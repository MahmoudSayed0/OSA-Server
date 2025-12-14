from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from chatlog.models import UserKnowledgeBase

User = get_user_model()


class Command(BaseCommand):
    help = 'Migrate legacy UserKnowledgeBase users to new User model'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        legacy_users = UserKnowledgeBase.objects.all()
        migrated = 0
        skipped = 0
        errors = 0

        self.stdout.write(f'Found {legacy_users.count()} legacy users to process')

        for legacy_user in legacy_users:
            # Check if already migrated
            if User.objects.filter(legacy_user_kb_id=legacy_user.id).exists():
                self.stdout.write(f'  SKIP: {legacy_user.username} (already migrated)')
                skipped += 1
                continue

            # Check if username already exists
            if User.objects.filter(username=legacy_user.username).exists():
                self.stdout.write(
                    self.style.WARNING(f'  SKIP: {legacy_user.username} (username already exists)')
                )
                skipped += 1
                continue

            # Create placeholder email from username
            username = legacy_user.username or f'user_{legacy_user.id}'
            email = f"{username}@legacy.oinride.local"

            if dry_run:
                self.stdout.write(f'  WOULD MIGRATE: {username} -> {email}')
                migrated += 1
                continue

            try:
                new_user = User.objects.create(
                    username=username,
                    email=email,
                    collection_name=legacy_user.collection_name,
                    migrated_from_legacy=True,
                    legacy_user_kb_id=legacy_user.id,
                )
                # Set unusable password - user will need to reset or use Google OAuth
                new_user.set_unusable_password()
                new_user.save()

                self.stdout.write(self.style.SUCCESS(f'  MIGRATED: {username}'))
                migrated += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ERROR: {username} - {str(e)}')
                )
                errors += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Migration complete:'))
        self.stdout.write(f'  - Migrated: {migrated}')
        self.stdout.write(f'  - Skipped: {skipped}')
        self.stdout.write(f'  - Errors: {errors}')

        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'This was a dry run. Run without --dry-run to apply changes.'
            ))
