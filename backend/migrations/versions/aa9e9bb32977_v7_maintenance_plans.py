"""v7: preventive-maintenance plans

Revision ID: aa9e9bb32977
Revises: 601cf542efaa
Create Date: 2026-08-16 15:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'aa9e9bb32977'
down_revision = '601cf542efaa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'maintenance_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=False),
        sa.Column('service_type', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('last_service_on', sa.Date(), nullable=True),
        sa.Column('next_due_on', sa.Date(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('maintenance_plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_maintenance_plans_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_plans_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_plans_next_due_on'), ['next_due_on'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('maintenance_plans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_maintenance_plans_next_due_on'))
        batch_op.drop_index(batch_op.f('ix_maintenance_plans_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_plans_organization_id'))

    op.drop_table('maintenance_plans')
