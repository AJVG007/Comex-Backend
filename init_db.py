from database import Base, engine, SessionLocal
from models import User
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Crear tablas
Base.metadata.create_all(bind=engine)

# Sesión
db = SessionLocal()

# Crear usuario admin si no existe
admin = db.query(User).filter(User.username == "admin").first()

if not admin:
    hashed_password = pwd_context.hash("Admin123.")
    new_user = User(
        username="admin",
        email="jair.velasco@tecnosinergia.com",
        password_hash=hashed_password
    )
    db.add(new_user)
    db.commit()
    print("✅ Usuario admin creado")
else:
    print("ℹ️ Usuario admin ya existe")
