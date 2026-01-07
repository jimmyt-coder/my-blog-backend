# --- 1. 标准库 (Standard Library) ---
import cloudinary
import cloudinary.uploader
import os
import json
from datetime import datetime, timezone

# --- 2. 第三方库 (Third Party) ---
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# --- Cloudinary 感应配置 ---
# 第一行：获取云端名称。如果拿不到，说明是本地环境，下面的 config 就不执行
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')

if CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        # 第二行：获取 API Key
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        # 第三行：获取 API Secret
        api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        secure=True
    )

# --- 初始化配置 ---
app = Flask(__name__)
# CORS(app)
# 允许所有来源访问，或者等部署后填入 Render 网址
CORS(app, resources={r"/*": {"origins": "*"}})

# --- A. 辅助函数 ---
def remove_physical_file(url):
    """仅仅负责：删除本地硬盘上的旧文件"""
    if not url or url.startswith('http'): 
        return
    try:
        # 确保路径拼接正确：app.root_path 通常是项目根目录
        # .lstrip('/') 是为了防止 join 时把 /static 识别为绝对路径
        file_path = os.path.join(app.root_path, url.lstrip('/'))
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"清理文件失败: {e}")   

# 路径管理
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
upload_path = os.path.join(basedir, 'static', 'uploads')

# 自动创建必要的物理目录
os.makedirs(instance_path, exist_ok=True)
os.makedirs(upload_path, exist_ok=True)

# --- 数据库连接配置 ---
# 1. 优先读取 Render 提供的 DATABASE_URL，没有则用本地 travel.db
db_url = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(instance_path, 'travel.db')}")

# 2. 修复 SQLAlchemy 1.4+ 版本对 postgresql:// 协议头的强制要求
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# 3. 统一应用配置
app.config.update(
    SQLALCHEMY_DATABASE_URI=db_url,      # 👈 这里现在是动态的了
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=upload_path,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024 
)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# 智能上传
def smart_upload(file):
    if not file or file.filename == '':
        return None
    
    # 云端：感应到 Render 环境变量就传 Cloudinary
    if os.getenv('CLOUDINARY_CLOUD_NAME'):
        upload_result = cloudinary.uploader.upload(file)
        return upload_result['secure_url']
    
    # 本地模式
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return f"/static/uploads/{filename}"

# --- 数据库模型 ---
class User(db.Model):
    __tablename__ = 'user'  # user保持单数
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='commenter', lazy=True)

class Post(db.Model):
    __tablename__ = 'post'  # post保持单数
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # 指向 user
    
    # 统一使用 UTC 时间，并增加更新时间自动触发
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    images = db.relationship('PostImage', backref='post', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")

    def to_dict(self, include_comments=False):
        """保持原有的序列化字段，仅优化排版"""
        data = {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "image_url": self.image_url,
            "author": self.author.username if self.author else "Unknown",
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "images": [{"id": img.id, "url": img.url} for img in self.images]
        }
        if include_comments:
            data["comments"] = [c.to_dict() for c in self.comments]
        return data

class PostImage(db.Model):
    __tablename__ = 'post_image'  # 保持单数
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False) # 👈 关键修复：指向 post.id

class Comment(db.Model):
    __tablename__ = 'comment'  # 保持单数
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False) # 👈 关键修复：指向 post.id
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "text": self.text,
            "user_id": self.user_id,
            "author": self.commenter.username if self.commenter else "Anonymous",
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

# --- 路由逻辑 ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"message": "User already exists"}), 400
    
    # 💡 优化点：生成哈希密码，即使数据库泄露，原始密码也不会暴露
    hashed_password = generate_password_hash(data['password'])
    new_user = User(username=data['username'], password=hashed_password)
    
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "Registration successful"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    
    # 💡 优化点：使用专门的 check 函数。它会把输入的密码加盐后对比存储的哈希串
    if user and check_password_hash(user.password, data['password']):
        return jsonify({
            "message": "Login successful",
            "user_id": user.id,
            "username": user.username
        }), 200
        
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/api/users/<int:user_id>/posts', methods=['GET'])
def get_user_posts(user_id):
    try:
        # 使用已经实现的 joinedload 优化方案，防止 N+1 查询
        posts = Post.query.filter_by(user_id=user_id)\
            .options(joinedload(Post.author), joinedload(Post.images))\
            .order_by(Post.created_at.desc())\
            .all()
        
        return jsonify([p.to_dict() for p in posts]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/posts', methods=['GET'])
def get_posts():
    #  获取前端传来的搜索关键词 (例如 ?q=paris)
    search_query = request.args.get('q', '')

    #  基础查询）
    query = Post.query.options(
        joinedload(Post.author), 
        joinedload(Post.images)
    )

    #  如果有关键词，增加模糊匹配过滤
    if search_query:
        # ilike 表示忽略大小写的搜索，% 是通配符
        query = query.filter(
            (Post.title.ilike(f'%{search_query}%')) | 
            (Post.content.ilike(f'%{search_query}%'))
        )
        
    #  最后进行排序并执行查询
    posts = query.order_by(Post.created_at.desc()).all()
    
    return jsonify([p.to_dict() for p in posts]), 200

@app.route('/api/posts/<int:post_id>', methods=['GET'])
def get_post_detail(post_id):
    try:
        # 深度预加载：Post -> (Author, Images, Comments -> Commenter)
        post = Post.query.options(
            joinedload(Post.author),
            joinedload(Post.images),
            joinedload(Post.comments).joinedload(Comment.commenter)
        ).get_or_404(post_id)
        return jsonify(post.to_dict(include_comments=True)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/posts', methods=['POST'])
def create_post():
    try:
        new_post = Post(
            title=request.form.get('title'),
            content=request.form.get('content'),
            user_id=request.form.get('user_id')
        )

        # 封面图：一句话搞定，管它是本地还是云端
        if 'image' in request.files:
            new_post.image_url = smart_upload(request.files['image'])

        # 画廊图：同样一句话搞定
        if 'images' in request.files:
            for f in request.files.getlist('images'):
                url = smart_upload(f)
                if url:
                    db.session.add(PostImage(url=url, post=new_post))

        db.session.add(new_post)
        db.session.commit()
        return jsonify({"message": "OK", "id": new_post.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/static/uploads/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ... 图片上传和 PUT 接口保持之前的逻辑 ...
@app.route('/api/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files: 
        return jsonify({"message": "No file"}), 400
    
    file = request.files['file']
    # 生成带时间戳的文件名
    url = smart_upload(file)
    
    if url:
        return jsonify({"url": url}), 200
    return jsonify({"message": "Upload failed"}), 500

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = request.args.get('user_id', type=int)
    if user_id != post.user_id:
        return jsonify({"message": "Permission denied"}), 403
    db.session.delete(post)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200

# 编辑/更新博客内容
@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def update_post(post_id):
    post = Post.query.options(joinedload(Post.images)).get_or_404(post_id)
    
    # 权限校验
    user_id_from_client = request.form.get('user_id', type=int)
    if user_id_from_client != post.user_id:
        return jsonify({"message": "Permission denied"}), 403

    # 1. 更新基本字段
    post.title = request.form.get('title', post.title)
    post.content = request.form.get('content', post.content)

    # 2. 处理封面图删除/更换
    # 对应前端的 coverDeleted 逻辑
    if request.form.get('delete_cover') == 'true':
        post.image_url = None # 数据库清空

    # 对应前端的 newCoverFile 逻辑
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename:                      
            post.image_url = smart_upload(request.files['image'])

    # 3. 画廊图片精准删除
    # 因为前端传的是 JSON 字符串，所以这里要解析
    removed_ids_json = request.form.get('delete_image_ids', '[]')        
    try:
        # 2. 将字符串 "[1,2]" 解析为 Python 列表 [1,2]
        delete_image_ids = json.loads(removed_ids_json)
        
        if delete_image_ids:
            # 3. 这里的 PostImage.id.in_ 会处理列表里的每一个 ID
            images_to_del = PostImage.query.filter(
                PostImage.id.in_(delete_image_ids), 
                PostImage.post_id == post.id
            ).all()
            
            for img in images_to_del:
                # 4. 执行物理删除（从硬盘删掉文件）
                remove_physical_file(img.url) 
                # 5. 执行数据库删除
                db.session.delete(img)
                
            print(f"成功删除旧图数量: {len(images_to_del)}")
            
    except Exception as e:
        print(f"解析或删除画廊图片失败: {e}")

    # 4. 追加新上传的画廊图片
    if 'images' in request.files:
        gallery_files = request.files.getlist('images')
        for file in gallery_files:
            new_url = smart_upload(file) 
            if new_url:
                db.session.add(PostImage(url=new_url, post_id=post.id))
    try:
        db.session.commit()
        # 确保 Post 模型有 to_dict 方法，或者手动返回数据
        return jsonify({"message": "Update successful"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Server Error: {str(e)}"}), 500

@app.route('/api/posts/<int:post_id>/comments', methods=['POST'])
def add_comment(post_id):
    data = request.json
    new_comment = Comment(text=data['text'], user_id=data['user_id'], post_id=post_id)
    db.session.add(new_comment)
    db.session.commit()
    return jsonify(new_comment.to_dict()), 201

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    user_id = request.args.get('user_id', type=int)
    if user_id in [comment.user_id, comment.post.user_id]:
        db.session.delete(comment)
        db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    return jsonify({"message": "Denied"}), 403

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # 修改这里：添加 host='0.0.0.0'，去掉 debug=True
    # Render 会自动分配端口，但在本地运行测试时它依然默认 5000
    app.run(host='0.0.0.0', port=5000)