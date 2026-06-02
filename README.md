# IA SETORIZAR

Aplicativo desktop em Python para classificar produtos do arquivo `SMG11.F170.csv` em setores válidos usando o Gemini via Selenium.

## Instalação

```bash
python -m pip install -r requirements.txt
```

## Configuração

1. Edite `URL_APPS_SCRIPT` em `ia_setorizar.py` caso queira sincronizar o status com Google Apps Script.
2. Confirme os caminhos Windows configurados no script:
   - `C:\Users\saaesilva\Desktop\Arquivos\SMG11.F170.csv`
   - `C:\Users\saaesilva\Desktop\SMG11.F170.csv`
   - `C:\Users\saaesilva\Desktop\IA SETORIZAR`

## Execução

```bash
python ia_setorizar.py
```

Na primeira execução, o Chrome abrirá o Gemini e poderá solicitar login na conta corporativa. Depois disso, clique em **Iniciar Robô** para processar os lotes.
