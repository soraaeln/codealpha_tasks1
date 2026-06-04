import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')

import django
django.setup()

from store.models import Announcement
a = Announcement.objects.filter(is_active=True).first()
if a:
    a.title = "Mother's Day Special<br/>Bouquets Are Here"
    a.content = "Give mom the gift she truly deserves. Our exclusive arrangements start at just Rs. 1,299."
    a.save()
    print(f"Updated: {a.title}")