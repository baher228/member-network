import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy import text
from app.db import engine


def normal_name(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def normal_url(value):
    if not value or not value.strip():
        return None
    url = urlsplit(value.strip())
    if url.scheme.lower() not in ('http', 'https') or not url.hostname or url.username or url.password:
        raise ValueError('Expected an absolute HTTP(S) URL without credentials')
    return urlunsplit(('https', url.netloc.lower(), url.path.rstrip('/'), '', ''))


def submit_questionnaire(body):
    fields = body.model_dump()
    fields['email'] = body.email.strip().casefold() if body.email else None
    fields['luma_profile_url'] = normal_url(fields.get('luma_profile_url'))
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(7349853)'))
        existing = list(conn.execute(text('SELECT id,name,luma_profile_url,email,opted_in FROM members WHERE is_seed=false')).mappings())
        matches = [m for m in existing if fields['luma_profile_url'] and m['luma_profile_url'] == fields['luma_profile_url']]
        if not matches and fields['email']:
            matches = [m for m in existing if normal_name(m['name']) == normal_name(fields['name'])
                       and m['email'] and m['email'].strip().casefold() == fields['email']]
        if len(matches) > 1:
            raise ValueError('Ambiguous member identity; supply a unique Luma profile URL')
        if matches:
            if not fields['luma_profile_url']:
                fields.pop('luma_profile_url')
            assignments = ','.join(f'{key}=:{key}' for key in fields)
            result = conn.execute(text(f'UPDATE members SET {assignments},opted_in=true WHERE id=:id RETURNING *'),
                                  dict(**fields, id=matches[0]['id'])).mappings().one()
        else:
            result = conn.execute(text(f'INSERT INTO members ({",".join(fields)},opted_in) VALUES '
                f'({",".join(":"+key for key in fields)},true) RETURNING *'), fields).mappings().one()
        return dict(result)
