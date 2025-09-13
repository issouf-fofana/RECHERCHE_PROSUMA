from django.db import migrations, models

def copy_old_to_new(apps, schema_editor):
    CompareConfig = apps.get_model("configs", "CompareConfig")
    for cfg in CompareConfig.objects.all():
        # ancien schéma: join_key_* peut être str ou list
        w1 = cfg.join_key_web1
        ds = cfg.join_key_desktop

        if isinstance(w1, str):
            w1_list = [w1] if w1 else []
        elif isinstance(w1, list):
            w1_list = w1
        else:
            w1_list = []

        if isinstance(ds, str):
            ds_list = [ds] if ds else []
        elif isinstance(ds, list):
            ds_list = ds
        else:
            ds_list = []

        # écrire dans les nouvelles colonnes JSON
        cfg.join_key_web1_new = w1_list
        cfg.join_key_desktop_new = ds_list
        cfg.save(update_fields=["join_key_web1_new", "join_key_desktop_new"])

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("configs", "0001_initial"),
    ]

    operations = [
        # 1) Ajouter deux nouvelles colonnes JSON (avec [] par défaut)
        migrations.AddField(
            model_name="compareconfig",
            name="join_key_web1_new",
            field=models.JSONField(default=list, null=True),
        ),
        migrations.AddField(
            model_name="compareconfig",
            name="join_key_desktop_new",
            field=models.JSONField(default=list, null=True),
        ),
        # 2) Copier les anciennes valeurs → nouvelles colonnes (en listes)
        migrations.RunPython(copy_old_to_new, reverse_code=noop),
        # 3) Supprimer les anciennes colonnes
        migrations.RemoveField(
            model_name="compareconfig",
            name="join_key_web1",
        ),
        migrations.RemoveField(
            model_name="compareconfig",
            name="join_key_desktop",
        ),
        # 4) Renommer NEW → noms finaux
        migrations.RenameField(
            model_name="compareconfig",
            old_name="join_key_web1_new",
            new_name="join_key_web1",
        ),
        migrations.RenameField(
            model_name="compareconfig",
            old_name="join_key_desktop_new",
            new_name="join_key_desktop",
        ),
    ]
