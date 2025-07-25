import cloudscraper

def descargar_html_jugador(player_id: str):
    url = f"https://dpm.lol/pro/{player_id}"
    print(f"🌐 Descargando página: {url}")
    
    # Crea scraper que evita bloqueos de Cloudflare
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url)

    if response.status_code == 200:
        filename = f"{player_id}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"✅ HTML guardado como: {filename}")
    else:
        print(f"❌ Error al acceder a la página: Código {response.status_code}")

if __name__ == "__main__":
    descargar_html_jugador("Jojopyun")