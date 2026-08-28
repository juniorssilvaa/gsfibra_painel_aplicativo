"""
PostgreSQL SERIAL/identity drift after imports with explicit PKs — realign sequence to MAX(id).
"""
import logging

from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def repair_model_pk_sequence(model) -> bool:
    """
    Set the sequence for model's primary key column so the next INSERT uses MAX(pk)+1.
    Returns False if not PostgreSQL, if there is no serial sequence (e.g. UUID), or on error.
    """
    if connection.vendor != 'postgresql':
        return False

    table = model._meta.db_table
    col = model._meta.pk.column
    qn = connection.ops.quote_name

    sql = (
        "SELECT setval(pg_get_serial_sequence(%s, %s), "
        f"COALESCE((SELECT MAX({qn(col)}) FROM {qn(table)}), 0), "
        "true)"
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, [table, col])
    except (ProgrammingError, OperationalError) as e:
        logger.warning(
            "repair_model_pk_sequence skipped for %s: %s",
            model._meta.label_lower,
            e,
        )
        return False
    return True
