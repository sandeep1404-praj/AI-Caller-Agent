"""Pytest configuration and fixtures."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Teacher, Lecture


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_teacher(db_session):
    teacher = Teacher(
        teacher_id="T001",
        name="Professor Amit Sharma",
        phone_number="+91-9876543210",
        department="Computer Science",
    )
    db_session.add(teacher)
    db_session.commit()
    return teacher


@pytest.fixture
def sample_lecture(db_session, sample_teacher):
    lecture = Lecture(
        teacher_id=sample_teacher.id,
        subject="Database Management Systems",
        lecture_date=datetime(2026, 8, 1, 10, 0),
        lecture_time="10:00 AM",
        room="Lab-301",
    )
    db_session.add(lecture)
    db_session.commit()
    return lecture
