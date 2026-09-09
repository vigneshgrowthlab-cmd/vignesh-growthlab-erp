from app.db.session import engine
from sqlalchemy import text
with engine.connect() as c:
    cols = [
        'ALTER TABLE activity_logs ADD COLUMN module VARCHAR(50)',
        'ALTER TABLE activity_logs ADD COLUMN record_id INT',
        'ALTER TABLE activity_logs ADD COLUMN record_type VARCHAR(50)',
        'ALTER TABLE activity_logs ADD COLUMN old_values TEXT',
        'ALTER TABLE activity_logs ADD COLUMN new_values TEXT',
        'ALTER TABLE activity_logs ADD COLUMN ip_address VARCHAR(45)',
        'ALTER TABLE activity_logs ADD COLUMN resource_id INT',
        'ALTER TABLE activity_logs ADD COLUMN resource_type VARCHAR(50)',
        'ALTER TABLE activity_logs ADD COLUMN details TEXT',
    ]
    for sql in cols:
        col = sql.split('COLUMN ')[1].split(' ')[0]
        try: c.execute(text(sql)); c.commit(); print('Added: ' + col)
        except Exception as e: print('Skip: ' + col if 'Duplicate' in str(e) else 'Err ' + col + ': ' + str(e)[:50])
print('Done')