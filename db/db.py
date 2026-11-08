import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)


DATABASE_URL = os.getenv("DATABASE_URL")


url = make_url(DATABASE_URL)


if url.get_backend_name() == "postgresql":
    url = url.set(drivername="postgresql+asyncpg")


# Async database engine
engine = create_async_engine(
    url,
    echo=False,
    pool_pre_ping=True,
)

# Async session factory
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)

# Database dependency for FastAPI
async def get_db():
    async with SessionLocal() as session:
        yield session


# Close database connections during application shutdown
async def close_db():
    await engine.dispose()



# For sychornize db 

# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker

# # Create the Engine
# engine = create_engine(
#     DATABASE_URL,
#     echo=False,  # Prints SQL queries (good for development)
# )

# # Create a Session factory
# Session = sessionmaker(
#     bind=engine,
#     autoflush=False,
#     autocommit=False,
# )