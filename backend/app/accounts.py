import hashlib
import os
import secrets
import smtplib
import time
from email.message import EmailMessage
from urllib.parse import urlparse
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from .database import DB, User, Session, Reset, Resource, Artifact

router=APIRouter(prefix="/api")
hasher=PasswordHasher()
COOKIE="fraudshield_session"
def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
def csrf(value):
    return digest("csrf:"+value)
def current(request, required=True):
    token=request.cookies.get(COOKIE,"")
    with DB() as db:
        session=db.get(Session,digest(token))
        if not session or session.expires<time.time():
            if required:
                raise HTTPException(401,"Sign in to your private workspace.")
            return None
        user=db.get(User,session.user_id)
        return user.id if user else None

def require_csrf(request):
    if request.method in {"POST","PUT","PATCH","DELETE"} and request.cookies.get(COOKIE):
        supplied=request.headers.get("x-csrf-token","")
        if not secrets.compare_digest(supplied,csrf(request.cookies[COOKIE])):
            raise HTTPException(403,"Missing or invalid CSRF token.")

class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=12,max_length=128)

def email(value):
    value=value.strip().lower()
    if "@" not in value or "." not in value.split("@")[-1]:
        raise HTTPException(422,"Enter a valid email address.")
    return value

def session_response(response,user_id):
    token=secrets.token_urlsafe(32)
    with DB() as db:
        db.execute(delete(Session).where(Session.expires<time.time()))
        db.add(Session(token=digest(token),user_id=user_id,expires=time.time()+86400))
        db.commit()
    response.set_cookie(COOKIE,token,httponly=True,secure=os.getenv("COOKIE_SECURE","false").lower()=="true",samesite="strict",max_age=86400,path="/")
    return {"user_id":user_id,"csrf_token":csrf(token)}

@router.post("/auth/register",status_code=201)
def register(body:Credentials,response:Response):
    with DB() as db:
        user=User(email=email(body.email),password=hasher.hash(body.password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,"Unable to register with this email.")
        return session_response(response,user.id)

@router.post("/auth/login")
def login(body:Credentials,response:Response):
    with DB() as db:
        user=db.scalar(select(User).where(User.email==email(body.email)))
        # Hash verification also runs for nonexistent accounts to reduce timing differences.
        hashed=user.password if user else hasher.hash("unavailable-account-password")
        try:
            valid=hasher.verify(hashed,body.password)
        except (VerifyMismatchError,InvalidHashError):
            valid=False
        if not user or not valid:
            raise HTTPException(401,"Invalid email or password.")
        return session_response(response,user.id)

@router.get("/auth/me")
def me(request:Request):
    identity=current(request)
    with DB() as db:
        user=db.get(User,identity)
        return {"user_id":identity,"email":user.email,"csrf_token":csrf(request.cookies[COOKIE])}

@router.post("/auth/logout")
def logout(request:Request,response:Response):
    with DB() as db:
        db.execute(delete(Session).where(Session.token==digest(request.cookies.get(COOKIE,""))));db.commit()
    response.delete_cookie(COOKIE,path="/")
    return {"logged_out":True}

class ResetRequest(BaseModel):
    email:str=Field(max_length=254)

def deliver_reset(address,token):
    host=os.getenv("SMTP_HOST")
    if not host:
        return
    message=EmailMessage()
    message["Subject"]="FraudShield password reset"
    message["From"]=os.getenv("SMTP_FROM","noreply@localhost")
    message["To"]=address
    origin=os.getenv("PUBLIC_ORIGIN","http://localhost:3000")
    message.set_content(f"Reset token: {token}\nOpen {origin}/ and use Account workspace → Reset password. Token expires in 15 minutes.")
    with smtplib.SMTP(host,int(os.getenv("SMTP_PORT","587")),timeout=10) as smtp:
        if os.getenv("SMTP_TLS","true").lower()=="true":
            smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)

@router.post("/auth/forgot-password")
def forgot(body:ResetRequest):
    with DB() as db:
        user=db.scalar(select(User).where(User.email==email(body.email)))
        if user:
            token=secrets.token_urlsafe(32)
            db.execute(delete(Reset).where(Reset.user_id==user.id))
            db.add(Reset(token=digest(token),user_id=user.id,expires=time.time()+900));db.commit()
            try:
                deliver_reset(user.email,token)
            except (OSError,smtplib.SMTPException):
                pass  # Never expose account existence or SMTP errors in the public response.
    return {"message":"If configured and eligible, reset instructions will be sent."}

class NewPassword(BaseModel):
    token:str=Field(min_length=20,max_length=128)
    password:str=Field(min_length=12,max_length=128)

@router.post("/auth/reset-password")
def reset(body:NewPassword):
    with DB() as db:
        record=db.get(Reset,digest(body.token))
        if not record or record.expires<time.time():
            raise HTTPException(400,"Invalid or expired reset token.")
        user=db.get(User,record.user_id);user.password=hasher.hash(body.password)
        db.execute(delete(Session).where(Session.user_id==user.id))
        db.execute(delete(Reset).where(Reset.user_id==user.id));db.commit()
    return {"reset":True}

@router.delete("/auth/account")
def remove_account(request:Request,response:Response):
    identity=current(request)
    with DB() as db:
        db.execute(delete(User).where(User.id==identity));db.commit()
    response.delete_cookie(COOKIE,path="/")
    return {"deleted":True}

class Saved(BaseModel):
    kind:str=Field(pattern="^(dataset|investigation|report)$")
    name:str=Field(min_length=1,max_length=100)
    payload:dict

@router.post("/workspace/resources",status_code=201)
def save(body:Saved,request:Request):
    import json
    identity=current(request)
    with DB() as db:
        # Bounded per-user retention for this small deployment.
        from sqlalchemy import func
        count=db.scalar(select(func.count()).select_from(Resource).where(Resource.user_id==identity))
        if count>=50:
            raise HTTPException(409,"Workspace limit: 50 saved resources. Delete old items first.")
        row=Resource(user_id=identity,kind=body.kind,name=body.name,payload=json.dumps(body.payload,allow_nan=False))
        db.add(row);db.commit()
        return {"id":row.id}

@router.get("/workspace/resources")
def resources(request:Request):
    identity=current(request)
    with DB() as db:
        return [{"id":r.id,"kind":r.kind,"name":r.name,"created":r.created} for r in db.scalars(select(Resource).where(Resource.user_id==identity).order_by(Resource.created.desc()))]

@router.get("/workspace/resources/{resource_id}")
def resource(resource_id:str,request:Request):
    import json
    identity=current(request)
    with DB() as db:
        row=db.get(Resource,resource_id)
        if not row or row.user_id!=identity:
            raise HTTPException(404,"Resource not found.")
        return {"id":row.id,"kind":row.kind,"name":row.name,"payload":json.loads(row.payload)}

@router.delete("/workspace/resources/{resource_id}")
def remove_resource(resource_id:str,request:Request):
    identity=current(request)
    with DB() as db:
        row=db.get(Resource,resource_id)
        if not row or row.user_id!=identity:
            raise HTTPException(404,"Resource not found.")
        db.delete(row);db.commit()
    return {"deleted":True}
