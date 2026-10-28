"""Generate a VAPID key pair for Web Push. Run once, then put the values in .env:

    python manage.py gen_vapid

The private key is emitted as ONE-LINE base64 of the DER (PKCS8) bytes. A single
line avoids all the newline/quoting pain that PEM has inside a .env file. The
server converts it back to a key object before sending.
  - VAPID_PUBLIC_KEY  -> base64url of the uncompressed EC point (~87 chars)
  - VAPID_PRIVATE_KEY -> base64 of DER PKCS8 (one line, no newlines)
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a VAPID public/private key pair for Web Push."

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        pub_raw = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()

        # DER (PKCS8) -> standard base64, single line. No newlines to mangle in .env.
        priv_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        priv_b64 = base64.b64encode(priv_der).decode()

        self.stdout.write(self.style.SUCCESS("Add these to your .env then restart gunicorn:\n"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={pub_b64}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={priv_b64}")
        self.stdout.write("VAPID_CLAIM_EMAIL=mailto:admin@smartpips.ir")
        self.stdout.write(self.style.WARNING(
            "\nNo quotes needed now (single line). After changing keys, users must "
            "toggle notifications OFF then ON to re-subscribe with the new key."))
