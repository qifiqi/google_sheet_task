"""add navigation menu items

Revision ID: 20260518_nav_menu
Revises: 20260427_user_oncall
Create Date: 2026-05-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260518_nav_menu'
down_revision = '20260427_add_user_mobile_oncall_and_task_creator'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'navigation_menu_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('permission', sa.String(length=100), nullable=True),
        sa.Column('parent_key', sa.String(length=100), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_index('idx_navigation_menu_parent_sort', 'navigation_menu_items', ['parent_key', 'sort_order'])
    op.create_index(op.f('ix_navigation_menu_items_is_visible'), 'navigation_menu_items', ['is_visible'])
    op.create_index(op.f('ix_navigation_menu_items_parent_key'), 'navigation_menu_items', ['parent_key'])


def downgrade():
    op.drop_index(op.f('ix_navigation_menu_items_parent_key'), table_name='navigation_menu_items')
    op.drop_index(op.f('ix_navigation_menu_items_is_visible'), table_name='navigation_menu_items')
    op.drop_index('idx_navigation_menu_parent_sort', table_name='navigation_menu_items')
    op.drop_table('navigation_menu_items')
