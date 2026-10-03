"""M4 contributions and growth. Frozen DDL; no runtime model imports.

Nullable foreign-key columns use SQLite native ADD COLUMN to preserve existing
AI suggestion child references without disabling foreign-key enforcement.
"""

from alembic import op

revision = "0004_m4"
down_revision = "0003_m3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE contributions (\n\ttitle VARCHAR(200) NOT NULL, \n\tcontribution_type VARCHAR(30) NOT NULL, \n\toccurred_on VARCHAR(10) NOT NULL, \n\tproject_id VARCHAR(36), \n\tquestion_id VARCHAR(36), \n\tdetails JSON NOT NULL, \n\tconfirmed_at VARCHAR(40) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\towner_id VARCHAR(36) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tupdated_at VARCHAR(40) NOT NULL, \n\tdeleted_at VARCHAR(40), \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES projects (id), \n\tFOREIGN KEY(question_id) REFERENCES research_items (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_contributions_occurred_on ON contributions (occurred_on)")
    op.execute("CREATE INDEX ix_contributions_owner_id ON contributions (owner_id)")
    op.execute("CREATE INDEX ix_contributions_project_id ON contributions (project_id)")
    op.execute("CREATE INDEX ix_contributions_question_id ON contributions (question_id)")
    op.execute(
        "CREATE TABLE ability_tags (\n\tname VARCHAR(60) NOT NULL, \n\tdescription TEXT NOT NULL, \n\tarchived BOOLEAN NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\towner_id VARCHAR(36) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tupdated_at VARCHAR(40) NOT NULL, \n\tdeleted_at VARCHAR(40), \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_ability_name UNIQUE (owner_id, name), \n\tFOREIGN KEY(owner_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_ability_tags_owner_id ON ability_tags (owner_id)")
    op.execute(
        "CREATE TABLE growth_entries (\n\tkind VARCHAR(30) NOT NULL, \n\ttitle VARCHAR(200) NOT NULL, \n\toccurred_on VARCHAR(10) NOT NULL, \n\tproject_id VARCHAR(36), \n\tquestion_id VARCHAR(36), \n\tdetails JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\towner_id VARCHAR(36) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tupdated_at VARCHAR(40) NOT NULL, \n\tdeleted_at VARCHAR(40), \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_growth_kind CHECK (kind IN ('ability_instance','understanding_change')), \n\tFOREIGN KEY(project_id) REFERENCES projects (id), \n\tFOREIGN KEY(question_id) REFERENCES research_items (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_growth_entries_occurred_on ON growth_entries (occurred_on)")
    op.execute("CREATE INDEX ix_growth_entries_owner_id ON growth_entries (owner_id)")
    op.execute("CREATE INDEX ix_growth_entries_project_id ON growth_entries (project_id)")
    op.execute("CREATE INDEX ix_growth_entries_question_id ON growth_entries (question_id)")
    op.execute(
        "CREATE TABLE growth_entry_tags (\n\tentry_id VARCHAR(36) NOT NULL, \n\ttag_id VARCHAR(36) NOT NULL, \n\tPRIMARY KEY (entry_id, tag_id), \n\tFOREIGN KEY(entry_id) REFERENCES growth_entries (id), \n\tFOREIGN KEY(tag_id) REFERENCES ability_tags (id)\n)"
    )
    op.execute(
        "CREATE TABLE growth_revisions (\n\tid VARCHAR(36) NOT NULL, \n\tcontribution_id VARCHAR(36), \n\tentry_id VARCHAR(36), \n\ttag_id VARCHAR(36), \n\tversion INTEGER NOT NULL, \n\toperation VARCHAR(40) NOT NULL, \n\tsnapshot JSON NOT NULL, \n\tcreated_at VARCHAR(40) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_growth_revision_parent CHECK ((contribution_id IS NOT NULL) + (entry_id IS NOT NULL) + (tag_id IS NOT NULL) = 1), \n\tCONSTRAINT uq_contribution_revision UNIQUE (contribution_id, version), \n\tCONSTRAINT uq_growth_revision UNIQUE (entry_id, version), \n\tCONSTRAINT uq_tag_revision UNIQUE (tag_id, version), \n\tFOREIGN KEY(contribution_id) REFERENCES contributions (id), \n\tFOREIGN KEY(entry_id) REFERENCES growth_entries (id), \n\tFOREIGN KEY(tag_id) REFERENCES ability_tags (id)\n)"
    )
    op.execute(
        "CREATE INDEX ix_growth_revisions_contribution_id ON growth_revisions (contribution_id)"
    )
    op.execute("CREATE INDEX ix_growth_revisions_entry_id ON growth_revisions (entry_id)")
    op.execute("CREATE INDEX ix_growth_revisions_tag_id ON growth_revisions (tag_id)")
    op.execute(
        'CREATE TABLE growth_evidence (\n\tid VARCHAR(36) NOT NULL, \n\tcontribution_id VARCHAR(36), \n\tentry_id VARCHAR(36), \n\trecord_revision_id VARCHAR(36), \n\tm2_revision_id VARCHAR(36), \n\tcontribution_revision_id VARCHAR(36), \n\tsource_version_id VARCHAR(36), \n\tfield_path VARCHAR(100) NOT NULL, \n\tstart INTEGER, \n\t"end" INTEGER, \n\tquote TEXT NOT NULL, \n\tpurpose VARCHAR(20) NOT NULL, \n\treviewed_version INTEGER NOT NULL, \n\treviewed_dependencies JSON NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_growth_evidence_parent CHECK ((contribution_id IS NOT NULL) != (entry_id IS NOT NULL)), \n\tCONSTRAINT ck_growth_evidence_target CHECK ((record_revision_id IS NOT NULL) + (m2_revision_id IS NOT NULL) + (contribution_revision_id IS NOT NULL) = 1), \n\tCONSTRAINT ck_growth_source_record CHECK (source_version_id IS NULL OR record_revision_id IS NOT NULL), \n\tFOREIGN KEY(contribution_id) REFERENCES contributions (id), \n\tFOREIGN KEY(entry_id) REFERENCES growth_entries (id), \n\tFOREIGN KEY(record_revision_id) REFERENCES record_revisions (id), \n\tFOREIGN KEY(m2_revision_id) REFERENCES m2_revisions (id), \n\tFOREIGN KEY(contribution_revision_id) REFERENCES growth_revisions (id), \n\tFOREIGN KEY(source_version_id) REFERENCES source_versions (id)\n)'
    )
    op.execute(
        "CREATE INDEX ix_growth_evidence_contribution_id ON growth_evidence (contribution_id)"
    )
    op.execute(
        "CREATE INDEX ix_growth_evidence_contribution_revision_id ON growth_evidence (contribution_revision_id)"
    )
    op.execute("CREATE INDEX ix_growth_evidence_entry_id ON growth_evidence (entry_id)")
    op.execute("CREATE INDEX ix_growth_evidence_m2_revision_id ON growth_evidence (m2_revision_id)")
    op.execute(
        "CREATE INDEX ix_growth_evidence_record_revision_id ON growth_evidence (record_revision_id)"
    )
    op.execute(
        "CREATE TABLE growth_action_links (\n\taction_id VARCHAR(36) NOT NULL, \n\towner_id VARCHAR(36) NOT NULL, \n\trevision_id VARCHAR(36) NOT NULL, \n\tPRIMARY KEY (action_id), \n\tFOREIGN KEY(action_id) REFERENCES actions (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id), \n\tFOREIGN KEY(revision_id) REFERENCES growth_revisions (id)\n)"
    )
    op.execute("CREATE INDEX ix_growth_action_links_owner_id ON growth_action_links (owner_id)")
    op.execute(
        "CREATE INDEX ix_growth_action_links_revision_id ON growth_action_links (revision_id)"
    )
    op.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN contribution_id VARCHAR(36) REFERENCES contributions(id)"
    )
    op.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN contribution_revision_id VARCHAR(36) REFERENCES growth_revisions(id)"
    )


def downgrade():
    op.execute("ALTER TABLE ai_suggestions DROP COLUMN contribution_revision_id")
    op.execute("ALTER TABLE ai_suggestions DROP COLUMN contribution_id")
    op.drop_table("growth_action_links")
    op.drop_table("growth_evidence")
    op.drop_table("growth_revisions")
    op.drop_table("growth_entry_tags")
    op.drop_table("growth_entries")
    op.drop_table("ability_tags")
    op.drop_table("contributions")
