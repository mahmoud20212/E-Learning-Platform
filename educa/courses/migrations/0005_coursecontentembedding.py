# Generated manually for pgvector integration

from django.db import migrations, models
import django.db.models.deletion
import pgvector.django


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0004_course_students'),
    ]

    operations = [
        pgvector.django.VectorExtension(),
        migrations.CreateModel(
            name='CourseContentEmbedding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_order', models.PositiveIntegerField(db_index=True, default=0)),
                ('chunk_id', models.CharField(max_length=255, unique=True)),
                ('source', models.CharField(max_length=255)),
                ('title', models.CharField(blank=True, max_length=255)),
                ('content', models.TextField()),
                ('embedding', pgvector.django.VectorField(dimensions=384)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_embeddings', to='courses.course')),
                ('module', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='content_embeddings', to='courses.module')),
            ],
            options={
                'indexes': [models.Index(fields=['course', 'module_order'], name='courses_cou_course__9fffae_idx')],
            },
        ),
    ]
