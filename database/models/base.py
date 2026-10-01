from sqlalchemy.orm import DeclarativeBase, mapped_column


int_pk = mapped_column(primary_key=True)


class Base(DeclarativeBase):
    pass
