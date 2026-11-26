# Desenvolvimento

Use Python 3.12 e um ambiente virtual. Instale `requirements.txt`, `requirements-dev.txt` e `requirements-torch.txt`; em uma estação CUDA instale separadamente o wheel apropriado para o driver. No Linux, GTK usa a introspecção do sistema.

```bash
python manage.py collectstatic --yes
python manage.py assets verify
python -m tools.patch_vela_self_test
python manage.py self-test
python -m pytest -q
python manage.py runapp
```

Para provisionar os modelos nativos no ambiente de desenvolvimento, execute `python -m tools.provision_kokentau PACOTE_V7.zip PACOTE_V8.zip`. O carregamento é automático quando uma técnica Kokentau é acionada e os recursos locais ficam em `native-resources/kokentau`. Consulte [o build](BUILD.md) para distribuição e [a validação científica](KOKENTAU_V8_2.md) para o protocolo de comparação.
