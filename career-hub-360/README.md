# 🚀 Career Hub 360

Une seule plateforme Streamlit qui réunit **Carrer_hub**, **Carreer_hub**, **Joba_search** et **Radar Emploi**, organisée en
**5 agents indépendants**. Chaque agent a ses entrées, son bouton et ses résultats ; aucun n'attend les autres. Ils
partagent seulement des données (profil, modèles, offres collectées).

| Agent | Rôle | Sorties |
|---|---|---|
| 🧭 **Profil** | Lit le CV et la lettre modèles (Word / PDF), extrait le profil (postes visés, compétences, expérience), diagnostique le CV | Profil = critères de recherche |
| 🔎 **Chasseur d'offres** | Offres récentes selon le profil, sur des sources autorisées ; filtres (niveau, contrat, salaire, fraîcheur), note /100, doublons fusionnés — **bouton « Mettre à jour »** | Offres + liens pour candidater, recherches pré-remplies (LinkedIn, Indeed, APEC, WTTJ, cabinets) |
| ✍️ **Rédacteur CV & lettre** | Adapte le CV et la lettre modèles à l'offre **copiée-collée**, sans rien inventer | CV + lettre en **Word (.docx) et PDF**, score de correspondance avant / après |
| 📡 **Veille marché & conseil** | État du marché, attentes des recruteurs, salaires, plan d'action — **avec les liens des sources** ; compétences demandées vs profil | Rapport Word + PDF, graphiques |
| 🎤 **Coach entretien** | Questions probables pour l'offre, éléments attendus, évaluation des réponses | Fiche de préparation Word + PDF |

Plus : **Tableau de bord** (bouton de mise à jour global offres + veille), **Suivi & documents** (statuts de candidature,
tous les fichiers générés), **Réglages & aide**.

## Avec ou sans IA

Tout fonctionne sans IA (règles, mots-clés, banque de questions, statistiques des offres). Avec une clé d'IA :
réécriture complète du CV et de la lettre, extraction du profil, veille appuyée sur une **recherche web sourcée**,
questions et évaluation personnalisées. Fournisseurs : **Gemini** (offre gratuite, recherche Google intégrée), **Claude**,
**OpenAI**, **Ollama** (local).

Garde-fous du Rédacteur : aucune expérience, date, employeur, diplôme ou chiffre n'est ajouté ; une compétence absente du
CV n'est ajoutée que si vous cochez que vous la possédez ; toute modification qui introduit un chiffre inconnu ou allonge
trop un paragraphe (risque de 2e page) est annulée et signalée ; chaque modification est montrée avant / après.

## CV Word recommandé

Avec un CV **.docx**, le texte est réécrit à sa place : police, couleurs, colonnes, tableaux et zones de texte sont
conservés, et le PDF est produit par LibreOffice à l'identique. Avec un CV PDF, il est reconstruit dans une mise en page
simple. Dans la lettre Word, les balises `{{POSTE}}`, `{{ENTREPRISE}}`, `{{DATE}}`, `{{COMPETENCES}}`, `{{LIEU}}`,
`{{NOM}}` sont remplies automatiquement.

## Lancer en local

```bash
pip install -r requirements.txt
cp .env.example .env      # puis renseignez vos clés
streamlit run app.py
```
(ou double-cliquez `lancer.bat` sous Windows). Pour un PDF identique au Word, installez LibreOffice ; sinon le PDF est
mis en page par ReportLab.

## Streamlit Cloud (GitHub)

Poussez tout le dossier (sans `.env` ni `data/`). `packages.txt` installe LibreOffice. Collez les clés dans
*Settings → Secrets* (modèle : `.streamlit/secrets.toml.example`), puis *Reboot app*. Fichier principal : `app.py`.

## Clés

| Usage | Clé(s) |
|---|---|
| IA | `GEMINI_API_KEY` (aistudio.google.com) ou `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY` ou `OLLAMA_HOST` ; `LLM_PROVIDER` pour choisir |
| France Travail | `FT_CLIENT_ID`, `FT_CLIENT_SECRET` (francetravail.io, API « Offres d'emploi v2 ») |
| Google Emploi (LinkedIn, Indeed, WTTJ, APEC, HelloWork…) | `SERPAPI_KEY` |
| Jooble / Adzuna | `JOOBLE_KEY` / `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| Recherche web de secours | `TAVILY_API_KEY` (facultatif) |

## Sources d'offres

Uniquement des sources autorisées : API France Travail, Google Emploi via SerpApi, API Jooble et Adzuna, API publiques des
sites carrières (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee). LinkedIn, Indeed, WTTJ, APEC, HelloWork
et Jobteaser interdisent la collecte automatique : leurs offres arrivent via Google Emploi et l'agent fournit des
recherches pré-remplies. (Le scraping JobSpy des anciens Career Hub n'a pas été repris pour cette raison.)

## Structure

```
app.py                 navigation, clés, tableau de bord
agents/                les 5 agents (profil, chasseur, redacteur, veille, coach) + base commune
core/                  moteur Radar Emploi : sources, filtres, géographie, score, stockage SQLite
services/              IA multi-fournisseurs, recherche web, Word/PDF, lexique de compétences
ui/                    une page par agent + suivi + réglages
config/                profil.toml (critères par défaut), employeurs.csv (annuaire de 200 employeurs)
data/                  créé à l'exécution : profil, modèles, offres, documents (effacé au redémarrage sur Streamlit Cloud)
```
