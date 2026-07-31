"""Teacher repository and service."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models import Teacher

logger = logging.getLogger(__name__)


class TeacherService:
    """Business logic for teacher management."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self) -> list[Teacher]:
        return self.db.query(Teacher).order_by(Teacher.name).all()

    def get_by_id(self, teacher_id: str) -> Teacher | None:
        return self.db.query(Teacher).filter(Teacher.teacher_id == teacher_id).first()

    def get_by_db_id(self, db_id: int) -> Teacher | None:
        return self.db.query(Teacher).filter(Teacher.id == db_id).first()

    def create_or_update(
        self,
        teacher_id: str,
        name: str,
        phone_number: str,
        department: str,
    ) -> Teacher:
        teacher = self.get_by_id(teacher_id)
        if teacher:
            teacher.name = name
            teacher.phone_number = phone_number
            teacher.department = department
            teacher.updated_at = datetime.now()
        else:
            teacher = Teacher(
                teacher_id=teacher_id,
                name=name,
                phone_number=phone_number,
                department=department,
            )
            self.db.add(teacher)
        self.db.flush()
        return teacher
