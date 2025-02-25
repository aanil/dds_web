"""Authentication related functions/tools."""

####################################################################################################
# IMPORTS ################################################################################ IMPORTS #
####################################################################################################

# Standard library

# Installed
from jwt import DecodeError
from sqlalchemy.sql import func
import argon2
import jwt
import sqlalchemy

# Own modules
from dds_web.database import models
from dds_web import app, basic_auth, token_auth
from dds_web.api.errors import InvalidUserCredentialsError, DatabaseError

####################################################################################################
# FUNCTIONS ############################################################################ FUNCTIONS #
####################################################################################################


@basic_auth.get_user_roles
def get_user_roles(user):
    return get_user_roles_common(user)


@token_auth.get_user_roles
def get_user_roles(user):
    return get_user_roles_common(user)


def get_user_roles_common(user):
    if "a" in user.permissions:
        return "admin"
    else:
        return "user"


@token_auth.verify_token
def verify_token(token):
    try:
        data = jwt.decode(token, app.config.get("SECRET_KEY"), algorithms="HS256")
        username = data.get("user")
        if username:
            user = models.User.query.get(username)
            if user:
                return user
        return None
    except DecodeError:
        return None


@basic_auth.verify_password
def verify_password(username, password):
    user = models.User.query.get(username)
    if user and verify_password_argon2id(user.password, password):
        return user
    return None


def gen_argon2hash(
    password,
    time_cost=2,
    memory_cost=102400,
    parallelism=8,
    hash_len=32,
    salt_len=16,
    encoding="utf-8",
    version=argon2.low_level.Type.ID,
):
    """Generates Argon2id password hash to store in DB."""

    pw_hasher = argon2.PasswordHasher(
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=hash_len,
        salt_len=salt_len,
        encoding=encoding,
        type=version,
    )
    formated_hash = pw_hasher.hash(password)

    return formated_hash


def verify_password_argon2id(db_pw, input_pw):
    """Verifies that the password specified by the user matches
    the encoded password in the database."""

    # Setup Argon2 hasher
    password_hasher = argon2.PasswordHasher()

    # Verify the input password
    try:
        password_hasher.verify(db_pw, input_pw)
    except (
        argon2.exceptions.VerifyMismatchError,
        argon2.exceptions.VerificationError,
        argon2.exceptions.InvalidHash,
    ):
        return False

    # TODO (ina): Add check_needs_rehash?

    return True
