from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User

router = APIRouter(prefix="/auth", tags=["Auth"])

# Dependencia para sesión de BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/register")
def register_user(email: str, password: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    new_user = User(email=email, password=password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"msg": "Usuario registrado correctamente", "user_id": new_user.id}

@router.post("/login")
def login(email: str, password: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user or db_user.password != password:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return {"msg": "Login exitoso 🎉", "user_id": db_user.id}
