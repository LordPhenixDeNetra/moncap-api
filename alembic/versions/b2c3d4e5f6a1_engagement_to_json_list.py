"""Change engagement column from string enum to JSON list

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-07-29 17:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a1"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE adhesions
        ALTER COLUMN engagement TYPE JSON
        USING json_build_array(engagement::text)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE adhesions
        ALTER COLUMN engagement TYPE VARCHAR(200)
        USING (engagement->>0)
    """)
