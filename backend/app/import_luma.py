import argparse
import csv
import io
import json
from datetime import date, datetime
from pathlib import Path
from sqlalchemy import text
from app.db import engine
from app.services.member_identity import normal_name, normal_url

def _event_date(value: str) -> date:
    head = value.strip()[:10]
    if len(value.strip()) > 10 and value.strip()[10] in 'T ':
        return date.fromisoformat(head)
    return date.fromisoformat(head) if len(value.strip()) == 10 else datetime.fromisoformat(value.replace('Z', '+00:00')).date()


COLUMNS = ['name', 'luma_profile_url', 'x_url', 'instagram_url', 'linkedin_url', 'github_url',
           'website_url', 'event_name', 'event_url', 'event_date']
MAX_BYTES = 2 * 1024 * 1024


def parse_csv(content):
    if len(content) > MAX_BYTES:
        raise ValueError('CSV exceeds the 2 MiB limit')
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')), strict=True)
        if reader.fieldnames != COLUMNS:
            raise ValueError('CSV headers must be exactly: ' + ','.join(COLUMNS))
        records = []
        for number, row in enumerate(reader, 2):
            if len(records) >= 5000:
                raise ValueError('CSV exceeds the 5000-row limit')
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'CSV row {number}: wrong number of columns')
            row = {key: value.strip() for key, value in row.items()}
            if not row['name'] or not row['event_name'] or not row['event_url'] or not row['event_date']:
                raise ValueError(f'CSV row {number}: name, event name, URL and date are required')
            if len(row['name']) > 200 or any(len(value) > 2000 for value in row.values()):
                raise ValueError(f'CSV row {number}: field too long')
            try:
                for key in COLUMNS:
                    if key.endswith('_url'):
                        row[key] = normal_url(row[key])
                row['event_date'] = _event_date(row['event_date'])
            except ValueError:
                raise ValueError(f'CSV row {number}: invalid URL or ISO event date') from None
            records.append(row)
        return records
    except (UnicodeDecodeError, csv.Error):
        raise ValueError('Expected a valid UTF-8 CSV file') from None


def import_csv(content):
    records = parse_csv(content)
    counts = dict(rows=len(records), members_created=0, members_matched=0, events_created=0, attendance_created=0)
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(7349853)'))
        members = [dict(row) for row in conn.execute(text('SELECT * FROM members WHERE is_seed=false ORDER BY id')).mappings()]
        for record in records:
            profile = record['luma_profile_url']
            matches = [m for m in members if profile and m['luma_profile_url'] == profile]
            if not matches:
                matches = [m for m in members if normal_name(m['name']) == normal_name(record['name'])]
            if len(matches) > 1:
                raise ValueError('Ambiguous normalised name; provide distinct Luma profile URLs')
            links = {key: record[key] for key in ('luma_profile_url', 'x_url', 'instagram_url', 'linkedin_url', 'website_url')}
            links['github'] = record['github_url']
            if matches:
                member = matches[0]
                counts['members_matched'] += 1
                updates = {key: value for key, value in links.items() if value and not member.get(key)}
                if updates:
                    conn.execute(text('UPDATE members SET ' + ','.join(f'{key}=:{key}' for key in updates) + ' WHERE id=:id'), dict(**updates, id=member['id']))
                    member.update(updates)
            else:
                fields = dict(name=record['name'], builds='', wants='', speaker_topics='', consent_intros=False,
                              consent_speaker=False, opted_in=False, source='luma', **links)
                member = dict(conn.execute(text(f'INSERT INTO members ({",".join(fields)}) VALUES '
                    f'({",".join(":"+key for key in fields)}) RETURNING *'), fields).mappings().one())
                members.append(member)
                counts['members_created'] += 1
            event_fields = {key: record[key] for key in ('event_name', 'event_url', 'event_date')}
            event_id = conn.execute(text('''INSERT INTO events(event_name,event_url,event_date)
                VALUES (:event_name,:event_url,:event_date) ON CONFLICT (event_url) DO NOTHING RETURNING id'''), event_fields).scalar()
            if event_id is None:
                event_id = conn.execute(text('SELECT id FROM events WHERE event_url=:event_url'), event_fields).scalar_one()
            else:
                counts['events_created'] += 1
            counts['attendance_created'] += conn.execute(text('''INSERT INTO attendance(member_id,event_id)
                VALUES (:member_id,:event_id) ON CONFLICT DO NOTHING'''), dict(member_id=member['id'], event_id=event_id)).rowcount
    return counts


def main():
    parser = argparse.ArgumentParser(description='Import a private Luma CSV into the configured network schema')
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        with args.path.open('rb') as source:
            counts = import_csv(source.read(MAX_BYTES + 1))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Import failed: {exc if isinstance(exc, ValueError) else "could not read CSV"}\n')
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
