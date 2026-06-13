def journaliser(user, action, objet_type='', objet_uuid='', description='', request=None):
    from administration.models import PisteAudit
    ip = None
    ua = ''
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    PisteAudit.objects.create(
        user=user if user and user.is_authenticated else None,
        user_email=user.email if user and user.is_authenticated else '',
        action=action,
        objet_type=objet_type,
        objet_uuid=str(objet_uuid),
        description=description,
        ip_address=ip,
        user_agent=ua,
    )
