"""Make vocabulary language-aware.

`spanish` and `example_es` were honest names while the app taught one
language. They are renamed rather than replaced so the sixty seeded Spanish
rows and every UserVocabState pointing at them survive untouched: a rename is
a metadata change, where add-and-backfill-and-drop would briefly leave the
scheduler with no words to pick from.

The old uniqueness key was (topic, term). Language joins it because a
spelling is only unique within a language.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tutor', '0005_profile'),
    ]

    operations = [
        # Dropped first: it names the column that is about to be renamed.
        migrations.RemoveConstraint(
            model_name='vocabitem',
            name='uniq_vocabitem_topic_spanish',
        ),
        migrations.RenameField(
            model_name='vocabitem',
            old_name='spanish',
            new_name='term',
        ),
        migrations.RenameField(
            model_name='vocabitem',
            old_name='example_es',
            new_name='example',
        ),
        # Every existing row is Spanish, which is exactly what the default
        # backfills, so no data migration is needed.
        migrations.AddField(
            model_name='vocabitem',
            name='language',
            field=models.CharField(
                choices=[('Spanish', 'Spanish'), ('French', 'French'),
                         ('German', 'German'), ('Hindi', 'Hindi')],
                db_index=True, default='Spanish', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='vocabitem',
            name='romanisation',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AlterModelOptions(
            name='vocabitem',
            options={'ordering': ['language', 'topic', 'difficulty', 'term']},
        ),
        migrations.AddConstraint(
            model_name='vocabitem',
            constraint=models.UniqueConstraint(
                fields=('language', 'topic', 'term'),
                name='uniq_vocabitem_language_topic_term',
            ),
        ),
        migrations.AlterModelOptions(
            name='uservocabstate',
            options={'ordering': ['due_date', 'item__term']},
        ),
        migrations.AddField(
            model_name='conversationsession',
            name='language',
            field=models.CharField(
                choices=[('Spanish', 'Spanish'), ('French', 'French'),
                         ('German', 'German'), ('Hindi', 'Hindi')],
                db_index=True, default='Spanish', max_length=20,
            ),
        ),
        # A stored turn carries the tutor's line and the correction it gave.
        # Neither is Spanish any more.
        migrations.RenameField(
            model_name='turn',
            old_name='tutor_message_es',
            new_name='tutor_message',
        ),
        migrations.RenameField(
            model_name='turn',
            old_name='corrected_es',
            new_name='corrected',
        ),
        migrations.AlterField(
            model_name='profile',
            name='learning_language',
            field=models.CharField(
                choices=[('Spanish', 'Spanish'), ('French', 'French'),
                         ('German', 'German'), ('Hindi', 'Hindi')],
                default='Spanish', max_length=40,
            ),
        ),
    ]
