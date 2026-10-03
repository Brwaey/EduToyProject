"""M5-A fixed AI inputs, adoption provenance; no runtime model imports."""

import sqlalchemy as sa
from alembic import op

revision = "0005_m5a"
down_revision = "0004_m4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE ai_tasks ADD COLUMN parameters JSON NOT NULL DEFAULT '{}'")
    op.execute(
        "ALTER TABLE ai_tasks ADD COLUMN target_reflection_id VARCHAR(36) REFERENCES reflections(id)"
    )
    op.execute("ALTER TABLE ai_suggestions ADD COLUMN action_id VARCHAR(36) REFERENCES actions(id)")
    op.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN action_revision_id VARCHAR(36) REFERENCES m2_revisions(id)"
    )
    op.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN reflection_id VARCHAR(36) REFERENCES reflections(id)"
    )
    op.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN reflection_revision_id VARCHAR(36) REFERENCES m2_revisions(id)"
    )
    with op.batch_alter_table("ai_task_inputs", recreate="always") as batch:
        batch.drop_constraint("ck_ai_input_target", type_="check")
        batch.add_column(sa.Column("selected_current_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("action_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_ai_input_action_id", "actions", ["action_id"], ["id"])
        batch.add_column(sa.Column("action_revision_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_ai_input_action_revision_id", "m2_revisions", ["action_revision_id"], ["id"]
        )
        batch.add_column(sa.Column("reflection_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_ai_input_reflection_id", "reflections", ["reflection_id"], ["id"]
        )
        batch.add_column(sa.Column("reflection_revision_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_ai_input_reflection_revision_id", "m2_revisions", ["reflection_revision_id"], ["id"]
        )
        batch.add_column(sa.Column("contribution_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_ai_input_contribution_id", "contributions", ["contribution_id"], ["id"]
        )
        batch.add_column(sa.Column("contribution_revision_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_ai_input_contribution_revision_id",
            "growth_revisions",
            ["contribution_revision_id"],
            ["id"],
        )
        batch.add_column(sa.Column("entry_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_ai_input_entry_id", "growth_entries", ["entry_id"], ["id"])
        batch.add_column(sa.Column("entry_revision_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_ai_input_entry_revision_id", "growth_revisions", ["entry_revision_id"], ["id"]
        )
        batch.create_check_constraint(
            "ck_ai_input_target",
            "(record_id IS NOT NULL AND record_revision_id IS NOT NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NOT NULL AND item_revision_id IS NOT NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NOT NULL AND action_revision_id IS NOT NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NOT NULL AND reflection_revision_id IS NOT NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NOT NULL AND contribution_revision_id IS NOT NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NOT NULL AND entry_revision_id IS NOT NULL AND source_version_id IS NULL)",
        )
    op.execute(
        "CREATE TABLE ai_adoptions (\n\tid VARCHAR(36) NOT NULL, \n\towner_id VARCHAR(36) NOT NULL, \n\tsuggestion_id VARCHAR(36) NOT NULL, \n\trevision_id VARCHAR(36) NOT NULL, \n\tfinal_content JSON NOT NULL, \n\treview_info JSON NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id), \n\tUNIQUE (suggestion_id), \n\tFOREIGN KEY(suggestion_id) REFERENCES ai_suggestions (id), \n\tFOREIGN KEY(revision_id) REFERENCES m2_revisions (id)\n)"
    )
    op.execute("CREATE INDEX ix_ai_adoptions_owner_id ON ai_adoptions (owner_id)")
    op.execute("CREATE INDEX ix_ai_adoptions_revision_id ON ai_adoptions (revision_id)")
    op.execute(
        'CREATE TABLE ai_adoption_citations (\n\tid VARCHAR(36) NOT NULL, \n\tadoption_id VARCHAR(36) NOT NULL, \n\tinput_id VARCHAR(36) NOT NULL, \n\tfield VARCHAR(50) NOT NULL, \n\tstart INTEGER NOT NULL, \n\t"end" INTEGER NOT NULL, \n\tquote TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(adoption_id) REFERENCES ai_adoptions (id), \n\tFOREIGN KEY(input_id) REFERENCES ai_task_inputs (id)\n)'
    )
    op.execute(
        "CREATE INDEX ix_ai_adoption_citations_adoption_id ON ai_adoption_citations (adoption_id)"
    )


def downgrade():
    raise RuntimeError("M5-A包含新增材料类型，请停服恢复升级前备份；不进行丢失引用的自动降级")
