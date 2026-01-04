from app import app, db, User, Post

with app.app_context():
    users = User.query.all()
    posts = Post.query.all()
    print("--- Users in DB ---")
    for u in users:
        print(f"ID: {u.id}, Username: {u.username}")
    
    print("\n--- Posts in DB ---")
    for p in posts:
        print(f"ID: {p.id}, Title: {p.title}, Author ID: {p.user_id}")