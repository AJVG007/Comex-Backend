from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from database import get_db
from models import User

router = APIRouter(prefix="/auth", tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/login")
def login(username: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()

    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    # Aquí deberíamos devolver JWT, pero por ahora devolvemos info básica
    return {
        "access_token": f"fake-jwt-for-{user.username}",
        "token_type": "bearer"
    }
