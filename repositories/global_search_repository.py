"""Búsqueda acotada; únicamente fragmentos SQL constantes y parámetros enlazados."""

QUERIES = {
    "owners": "SELECT id, first_name || ' ' || last_name, identification FROM owners WHERE TRANSLATE(LOWER(first_name || ' ' || last_name || ' ' || identification || ' ' || phone), 'áéíóúüñ', 'aeiouun') LIKE :q ESCAPE '\\'",
    "pets": "SELECT p.id, p.name, o.first_name || ' ' || o.last_name FROM pets p JOIN owners o ON o.id=p.owner_id WHERE TRANSLATE(LOWER(p.name || ' ' || p.microchip_number || ' ' || o.first_name || ' ' || o.last_name), 'áéíóúüñ', 'aeiouun') LIKE :q ESCAPE '\\'",
    "appointments": "SELECT a.id, p.name, TO_CHAR(a.appointment_at, 'DD/MM/YYYY HH24:MI') FROM appointments a JOIN pets p ON p.id=a.pet_id JOIN owners o ON o.id=p.owner_id WHERE TRANSLATE(LOWER(p.name || ' ' || a.reason || ' ' || o.first_name || ' ' || o.last_name), 'áéíóúüñ', 'aeiouun') LIKE :q ESCAPE '\\'",
    "consultations": "SELECT c.id, p.name, TO_CHAR(c.started_at, 'DD/MM/YYYY HH24:MI') FROM consultations c JOIN pets p ON p.id=c.pet_id JOIN owners o ON o.id=p.owner_id WHERE TRANSLATE(LOWER(p.name || ' ' || c.reason || ' ' || o.first_name || ' ' || o.last_name), 'áéíóúüñ', 'aeiouun') LIKE :q ESCAPE '\\'",
}


def search(conn, text, modules):
    escaped = text.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    results = []
    with conn.cursor() as cur:
        for module in modules:
            cur.execute(QUERIES[module] + " ORDER BY 1 DESC FETCH FIRST 10 ROWS ONLY", {"q": "%" + escaped + "%"})
            results.extend((module, int(id_), title, detail or "") for id_, title, detail in cur.fetchall())
    return results
