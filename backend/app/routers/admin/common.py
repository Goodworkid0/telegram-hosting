"""Shared imports/deps for the admin router package (split from the
former monolithic admin.py). Domain modules do `from .common import *`."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, String, text, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
import os
from app.database import get_db, engine, Base
from app.ledger import record_balance_change, reconcile_user, commit_and_broadcast
from app.models import (
    User, UserRole, CryptoDeposit, WithdrawalRequest,
    WithdrawalStatus, AppSettings, ModAction, LedgerEntry,
)
from app.telegram import create_notification
from app.moderation import apply_ban
from app.schemas import (
    UserResponse,
    WithdrawalRequestResponse,
    SuccessResponse,
)
from jose import jwt
from app.auth import get_current_admin, get_current_moderator, get_current_active_user, SECRET_KEY, ALGORITHM
from app.config import IS_PRODUCTION
from pydantic import BaseModel as PydanticBaseModel
