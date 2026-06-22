# create_superuser.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esignification.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = 'admin'
email = 'yawo907@gmail.com'
password = '12345678@'

user, created = User.objects.get_or_create(
    username=username,
    defaults={
        'email': email,
        'is_active': True,
        'is_superuser': True
    }
)

if created:
    user.set_password(password)
    user.is_superuser = True
    user.save()
    print(f'✅ Superuser "{username}" créé avec succès !')
else:
    print(f'ℹ️ Le superuser "{username}" existe déjà.')