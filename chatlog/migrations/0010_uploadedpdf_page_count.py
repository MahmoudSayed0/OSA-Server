# Generated manually for page_count field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatlog', '0009_foundationdocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='uploadedpdf',
            name='page_count',
            field=models.IntegerField(default=0),
        ),
    ]
