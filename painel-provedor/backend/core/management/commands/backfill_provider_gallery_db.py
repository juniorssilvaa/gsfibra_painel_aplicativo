from django.core.management.base import BaseCommand

from core.models import ProviderGalleryImage
from core.provider_gallery_storage import get_provider_gallery_bytes


class Command(BaseCommand):
    help = 'Preenche arquivo_db das imagens da galeria a partir dos arquivos em disco (se existirem).'

    def handle(self, *args, **options):
        qs = ProviderGalleryImage.objects.filter(ativo=True).order_by('id')
        ok = skip = 0
        for img in qs:
            if img.arquivo_db:
                ok += 1
                continue
            data, _ = get_provider_gallery_bytes(img)
            if data:
                self.stdout.write(self.style.SUCCESS(f'  id={img.id} ({img.nome})'))
                ok += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'  id={img.id} ({img.nome}) sem arquivo — reenvie pela Galeria no painel'
                    )
                )
                skip += 1
        self.stdout.write(self.style.SUCCESS(f'Concluído: {ok} com bytes, {skip} sem fonte'))
