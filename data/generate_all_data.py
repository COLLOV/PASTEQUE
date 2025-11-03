import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Configuration commune
start_date = datetime.now() - timedelta(days=180)
nb_records = 500

output_dir = Path(__file__).resolve().parent / "raw"
output_dir.mkdir(parents=True, exist_ok=True)

print("🚀 Génération de tous les fichiers CSV...")
print("="*60)
print(f"Écriture des fichiers dans: {output_dir}")

# ============================================================================
# 1. TICKETS JIRA (IT INTERNE)
# ============================================================================

departements_it = [
    "Souscription",
    "Sinistres",
    "Service Client",
    "Comptabilité",
    "Ressources Humaines",
    "IT",
    "Commercial",
    "Direction",
    "Juridique",
    "Actuariat",
    "Marketing",
    "Recouvrement"
]

problemes = [
    {
        "resume": "Problème de réception d'emails sur téléphone",
        "description": "Impossible de recevoir mes emails professionnels sur mon iPhone. La synchronisation ne fonctionne plus depuis ce matin."
    },
    {
        "resume": "Impossibilité de se connecter au VPN",
        "description": "Le client VPN affiche une erreur 'Authentification échouée' alors que mes identifiants sont corrects."
    },
    {
        "resume": "Accès bloqué à l'application de gestion des sinistres",
        "description": "Message d'erreur 'Accès refusé' lors de la tentative de connexion à SINISTRA. Besoin d'un accès urgent."
    },
    {
        "resume": "Imprimante du 3ème étage hors service",
        "description": "L'imprimante Canon du service sinistres affiche un message d'erreur et ne répond plus."
    },
    {
        "resume": "Lenteur importante sur l'application métier",
        "description": "L'application de souscription est extrêmement lente depuis 2 jours. Les temps de chargement dépassent 30 secondes."
    },
    {
        "resume": "Mot de passe expiré - demande de réinitialisation",
        "description": "Mon mot de passe Active Directory a expiré et je n'arrive pas à le réinitialiser via le portail self-service."
    },
    {
        "resume": "Problème de connexion au réseau WiFi",
        "description": "Impossible de se connecter au WiFi d'entreprise. Le réseau est visible mais l'authentification échoue."
    },
    {
        "resume": "Logiciel Excel qui plante régulièrement",
        "description": "Excel se ferme automatiquement toutes les heures avec un message d'erreur. Perte de données non sauvegardées."
    },
    {
        "resume": "Demande d'installation de logiciel",
        "description": "Besoin d'installer Adobe Acrobat Pro pour la signature électronique des contrats."
    },
    {
        "resume": "Problème d'accès au lecteur réseau partagé",
        "description": "Le lecteur Z: (serveur FILESERVER01) n'est plus accessible. Message 'Chemin réseau introuvable'."
    },
    {
        "resume": "Téléphone fixe sans tonalité",
        "description": "Mon poste téléphonique ne fonctionne plus. Pas de tonalité et impossible de passer/recevoir des appels."
    },
    {
        "resume": "Problème d'envoi d'emails avec pièces jointes",
        "description": "Impossible d'envoyer des emails avec des pièces jointes supérieures à 5 Mo. Message d'erreur systématique."
    },
    {
        "resume": "Demande de création de compte utilisateur",
        "description": "Nouveau collaborateur arrivé ce matin. Besoin de créer son compte AD et ses accès aux applications métier."
    },
    {
        "resume": "Écran qui scintille - problème matériel",
        "description": "Mon écran Dell présente des scintillements constants. Cela devient difficile de travailler."
    },
    {
        "resume": "Clavier défectueux - touches qui ne répondent pas",
        "description": "Plusieurs touches du clavier (E, R, T) ne fonctionnent plus correctement. Besoin d'un remplacement."
    },
    {
        "resume": "Accès refusé au dossier partagé Comptabilité",
        "description": "Message 'Vous n'avez pas les autorisations nécessaires' lors de l'accès au dossier \\\\COMPTA\\Factures."
    },
    {
        "resume": "Problème de webcam pour les visioconférences",
        "description": "Ma webcam n'est pas détectée par Teams. Impossible de participer aux réunions vidéo."
    },
    {
        "resume": "Logiciel de gestion commerciale qui freeze",
        "description": "L'application CRM se fige régulièrement et nécessite un redémarrage forcé."
    },
    {
        "resume": "Demande d'augmentation de droits sur application",
        "description": "Besoin d'obtenir les droits administrateur sur l'application de tarification pour valider les devis."
    },
    {
        "resume": "Ordinateur portable très lent au démarrage",
        "description": "Mon PC met plus de 10 minutes à démarrer complètement. Performances dégradées."
    },
    {
        "resume": "Problème de synchronisation OneDrive",
        "description": "OneDrive indique 'Synchronisation en attente' depuis 48h. Les fichiers ne se synchronisent plus."
    },
    {
        "resume": "Impossible d'imprimer en recto-verso",
        "description": "L'option recto-verso n'apparaît plus dans les paramètres d'impression."
    },
    {
        "resume": "Badge d'accès désactivé",
        "description": "Mon badge ne fonctionne plus pour accéder au bâtiment. Refusé à tous les lecteurs."
    },
    {
        "resume": "Erreur lors de la sauvegarde sur serveur",
        "description": "Impossible de sauvegarder mes documents sur le serveur. Message 'Espace disque insuffisant'."
    },
    {
        "resume": "Demande de suppression de compte utilisateur",
        "description": "Collaborateur parti. Besoin de désactiver son compte et transférer ses données."
    },
    {
        "resume": "Problème de son lors des visioconférences",
        "description": "Les participants n'entendent pas ma voix lors des appels Teams. Le micro semble ne pas fonctionner."
    },
    {
        "resume": "Application mobile professionnelle qui crash",
        "description": "L'application mobile de gestion des sinistres se ferme automatiquement au démarrage."
    },
    {
        "resume": "Souris sans fil qui ne répond plus",
        "description": "La souris Bluetooth se déconnecte régulièrement. Nécessite un redémarrage du PC."
    },
    {
        "resume": "Demande de licence Office supplémentaire",
        "description": "Besoin d'une licence Microsoft Office pour le nouveau stagiaire du service comptabilité."
    },
    {
        "resume": "Problème d'affichage de caractères spéciaux",
        "description": "Les accents et caractères spéciaux s'affichent mal dans certaines applications."
    },
    {
        "resume": "Scanner qui ne fonctionne plus",
        "description": "Le scanner du service courrier ne numérise plus les documents. Voyant rouge allumé."
    },
    {
        "resume": "Problème de connexion à l'intranet",
        "description": "Impossible d'accéder à l'intranet de l'entreprise. Page blanche lors du chargement."
    },
    {
        "resume": "Demande de changement de mot de passe messagerie",
        "description": "Suspicion de compromission du compte email. Demande de réinitialisation immédiate."
    },
    {
        "resume": "Erreur lors de l'ouverture de fichiers PDF",
        "description": "Adobe Reader affiche 'Le fichier est endommagé' pour tous les PDFs reçus aujourd'hui."
    },
    {
        "resume": "Problème de partage d'écran sur Teams",
        "description": "Impossible de partager mon écran lors des réunions. Option grisée dans Teams."
    },
    {
        "resume": "Disque dur externe non reconnu",
        "description": "Le disque dur USB de sauvegarde n'est plus détecté par Windows."
    },
    {
        "resume": "Problème de certification électronique",
        "description": "Ma signature électronique a expiré. Besoin de renouveler le certificat."
    },
    {
        "resume": "Application de tarification qui ne se lance pas",
        "description": "Message d'erreur 'DLL manquante' au lancement de l'outil de calcul des primes."
    },
    {
        "resume": "Demande de transfert de poste téléphonique",
        "description": "Changement de bureau. Besoin de transférer mon numéro de poste vers le bureau 3.12."
    },
    {
        "resume": "Problème de messagerie instantanée",
        "description": "Teams indique 'Hors ligne' en permanence alors que j'ai une connexion internet."
    }
]

tickets = []
for i in range(1, nb_records + 1):
    probleme = random.choice(problemes)
    random_days = random.randint(0, 180)
    creation_date = start_date + timedelta(days=random_days)

    ticket = {
        "ticket_id": f"JIRA-{i:04d}",
        "resume": probleme["resume"],
        "description": probleme["description"],
        "creation_date": creation_date.strftime("%Y-%m-%d %H:%M:%S"),
        "departement": random.choice(departements_it)
    }
    tickets.append(ticket)

tickets.sort(key=lambda x: x["creation_date"])

with (output_dir / 'tickets_jira.csv').open('w', newline='', encoding='utf-8') as f:
    fieldnames = ['ticket_id', 'resume', 'description', 'creation_date', 'departement']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(tickets)

print("✅ tickets_jira.csv généré")

# ============================================================================
# 2. REMBOURSEMENTS SINISTRES
# ============================================================================

types_sinistre = [
    "Auto - Accident responsable",
    "Auto - Accident non-responsable",
    "Auto - Bris de glace",
    "Auto - Vol",
    "Auto - Incendie",
    "Habitation - Dégât des eaux",
    "Habitation - Vol",
    "Habitation - Incendie",
    "Habitation - Catastrophe naturelle",
    "Habitation - Bris de glace",
    "Santé - Hospitalisation",
    "Santé - Soins dentaires",
    "Santé - Optique",
    "Santé - Consultation spécialiste",
    "Santé - Médicaments",
    "Responsabilité civile",
    "Assistance juridique",
    "Protection juridique"
]

statuts = [
    "En attente de pièces",
    "En cours d'instruction",
    "Validé - En attente de paiement",
    "Remboursé",
    "Remboursé partiellement",
    "Rejeté - Franchise non atteinte",
    "Rejeté - Hors garantie",
    "Rejeté - Exclusion contractuelle",
    "En attente d'expertise",
    "Complément d'information requis"
]

commentaires = [
    "Dossier complet, traitement en cours",
    "Documents manquants : devis de réparation",
    "Attente rapport d'expertise",
    "Franchise de 150€ appliquée",
    "Remboursement selon barème conventionnel",
    "Plafond annuel atteint",
    "Garantie optionnelle non souscrite",
    "Sinistre déclaré hors délai",
    "Factures conformes, validation OK",
    "Réclamation client en cours",
    "Complément d'information demandé par email",
    "RIB en attente",
    "Virement effectué le {date}",
    "Accord amiable trouvé",
    "Contentieux en cours avec tiers",
    "Expert mandaté - Rendez-vous fixé",
    "Ticket support créé: JIRA-{num}",
    "Client contacté pour précisions",
    "Procédure accélérée appliquée",
    "Dossier prioritaire - sinistre majeur"
]

departements_sinistres = [
    "Sinistres Auto",
    "Sinistres Habitation",
    "Sinistres Santé",
    "Service Indemnisation",
    "Service Expertise",
    "Service Juridique"
]

remboursements = []
for i in range(1, nb_records + 1):
    random_days = random.randint(0, 180)
    date_declaration = start_date + timedelta(days=random_days)
    type_sinistre = random.choice(types_sinistre)

    if "Auto" in type_sinistre:
        montant_reclame = round(random.uniform(500, 15000), 2)
    elif "Habitation" in type_sinistre:
        montant_reclame = round(random.uniform(300, 25000), 2)
    elif "Santé" in type_sinistre:
        montant_reclame = round(random.uniform(50, 5000), 2)
    else:
        montant_reclame = round(random.uniform(200, 10000), 2)

    statut = random.choice(statuts)

    if "Remboursé" in statut and "partiellement" not in statut:
        franchise = random.choice([0, 150, 200, 300, 500])
        montant_rembourse = round(max(0, montant_reclame - franchise), 2)
    elif "partiellement" in statut:
        montant_rembourse = round(montant_reclame * random.uniform(0.6, 0.9), 2)
    elif "Rejeté" in statut:
        montant_rembourse = 0.00
    else:
        montant_rembourse = 0.00

    if "Remboursé" in statut:
        delai_traitement = random.randint(5, 45)
        date_remboursement = date_declaration + timedelta(days=delai_traitement)
        date_remboursement_str = date_remboursement.strftime("%Y-%m-%d")
    else:
        date_remboursement_str = ""

    if "Auto" in type_sinistre:
        departement = "Sinistres Auto"
    elif "Habitation" in type_sinistre:
        departement = "Sinistres Habitation"
    elif "Santé" in type_sinistre:
        departement = "Sinistres Santé"
    else:
        departement = random.choice(["Service Indemnisation", "Service Expertise", "Service Juridique"])

    commentaire = random.choice(commentaires)
    if "{date}" in commentaire:
        commentaire = commentaire.replace("{date}", date_remboursement_str if date_remboursement_str else "à venir")
    if "{num}" in commentaire:
        jira_num = random.randint(1, 500)
        commentaire = commentaire.replace("{num}", f"{jira_num:04d}")

    remboursement = {
        "sinistre_id": f"SIN-{i:05d}",
        "client_id": f"CLI-{random.randint(10000, 99999)}",
        "date_declaration": date_declaration.strftime("%Y-%m-%d"),
        "date_remboursement": date_remboursement_str,
        "type_sinistre": type_sinistre,
        "montant_reclame": f"{montant_reclame:.2f}",
        "montant_rembourse": f"{montant_rembourse:.2f}",
        "statut": statut,
        "departement": departement,
        "commentaire": commentaire
    }
    remboursements.append(remboursement)

remboursements.sort(key=lambda x: x["date_declaration"])

with (output_dir / 'myfeelback_remboursements.csv').open('w', newline='', encoding='utf-8') as f:
    fieldnames = [
        'sinistre_id', 'client_id', 'date_declaration', 'date_remboursement',
        'type_sinistre', 'montant_reclame', 'montant_rembourse', 'statut',
        'departement', 'commentaire'
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(remboursements)

print("✅ myfeelback_remboursements.csv généré")

# ============================================================================
# 3. FEEDBACK SOUSCRIPTIONS
# ============================================================================

types_contrat = [
    "Auto - Au tiers", "Auto - Tous risques", "Auto - Intermédiaire",
    "Habitation - Propriétaire", "Habitation - Locataire", "Habitation - Résidence secondaire",
    "Santé - Individuelle", "Santé - Famille", "Santé - Sénior",
    "Vie - Décès", "Vie - Épargne", "Protection juridique",
    "Responsabilité civile", "Assurance emprunteur"
]

canaux_souscription = ["En ligne", "Téléphone", "Agence", "Courtier", "Application mobile"]

commentaires_positifs_souscription = [
    "Processus très fluide et rapide", "Conseiller très professionnel et à l'écoute",
    "Documentation claire et complète", "Prix compétitif", "Souscription en ligne très intuitive",
    "Excellent accueil en agence", "Réponse rapide à mes questions", "Je recommande vivement",
    "Simplicité du parcours digital", "Conseiller patient et pédagogue"
]

commentaires_negatifs_souscription = [
    "Processus trop long et complexe", "Manque d'informations claires sur les garanties",
    "Prix plus élevé que la concurrence", "Difficultés techniques sur le site web",
    "Délai de traitement du dossier trop long", "Conseiller peu disponible",
    "Formulaire en ligne compliqué", "Pièces justificatives demandées excessives",
    "Pas assez d'explications sur les exclusions", "Attente téléphonique trop longue"
]

souscriptions = []
for i in range(1, nb_records + 1):
    random_days = random.randint(0, 180)
    date_feedback = start_date + timedelta(days=random_days)
    note_globale = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 15, 35, 35])[0]

    record = {
        "feedback_id": f"SOUSCR-{i:05d}",
        "client_id": f"CLI-{random.randint(10000, 99999)}",
        "date_feedback": date_feedback.strftime("%Y-%m-%d"),
        "type_contrat": random.choice(types_contrat),
        "canal": random.choice(canaux_souscription),
        "note_globale": note_globale,
        "clarte_informations": max(1, min(5, note_globale + random.randint(-1, 1))),
        "facilite_processus": max(1, min(5, note_globale + random.randint(-1, 1))),
        "temps_traitement": max(1, min(5, note_globale + random.randint(-1, 1))),
        "qualite_accompagnement": max(1, min(5, note_globale + random.randint(-1, 1))),
        "rapport_qualite_prix": max(1, min(5, note_globale + random.randint(-1, 1))),
        "commentaire": random.choice(commentaires_positifs_souscription if note_globale >= 4 else commentaires_negatifs_souscription),
        "recommanderait": "Oui" if note_globale >= 4 else ("Non" if note_globale <= 2 else "Peut-être")
    }
    souscriptions.append(record)

with (output_dir / 'myfeelback_souscriptions.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=souscriptions[0].keys())
    writer.writeheader()
    writer.writerows(souscriptions)

print("✅ myfeelback_souscriptions.csv généré")

# ============================================================================
# 4. FEEDBACK SERVICE CLIENT
# ============================================================================

motifs_contact = [
    "Question sur contrat", "Modification de contrat", "Résiliation",
    "Problème de paiement", "Demande d'attestation", "Information sur garanties",
    "Réclamation", "Déclaration de sinistre", "Suivi de dossier",
    "Demande de devis", "Question technique app/site", "Renouvellement"
]

canaux_contact = ["Téléphone", "Email", "Chat en ligne", "Application mobile", "Agence", "Formulaire web"]

service_client = []
for i in range(1, nb_records + 1):
    random_days = random.randint(0, 180)
    date_feedback = start_date + timedelta(days=random_days)
    note_globale = random.choices([1, 2, 3, 4, 5], weights=[8, 12, 20, 35, 25])[0]

    commentaires_positifs = [
        "Conseiller très efficace et sympathique", "Réponse rapide et précise",
        "Problème résolu immédiatement", "Très bonne écoute", "Conseiller compétent",
        "Prise en charge rapide", "Explications claires", "Service de qualité",
        "Disponibilité appréciée", "Professionnel et courtois"
    ]

    commentaires_negatifs = [
        "Temps d'attente beaucoup trop long", "Problème non résolu",
        "Conseiller pas assez informé", "Pas de rappel comme promis", "Réponse évasive",
        "Manque d'empathie", "Transféré plusieurs fois", "Information contradictoire",
        "Toujours en attente de solution", "Service décevant"
    ]

    record = {
        "feedback_id": f"SVCLI-{i:05d}",
        "client_id": f"CLI-{random.randint(10000, 99999)}",
        "date_feedback": date_feedback.strftime("%Y-%m-%d"),
        "motif_contact": random.choice(motifs_contact),
        "canal": random.choice(canaux_contact),
        "temps_attente": random.choice(["< 2 min", "2-5 min", "5-10 min", "10-20 min", "> 20 min"]),
        "temps_resolution": random.choice(["Immédiat", "< 24h", "1-3 jours", "3-7 jours", "> 7 jours"]),
        "note_globale": note_globale,
        "note_rapidite": max(1, min(5, note_globale + random.randint(-1, 1))),
        "note_competence": max(1, min(5, note_globale + random.randint(-1, 1))),
        "note_amabilite": max(1, min(5, note_globale + random.randint(-1, 1))),
        "probleme_resolu": "Oui" if note_globale >= 4 else ("Non" if note_globale <= 2 else "Partiellement"),
        "commentaire": random.choice(commentaires_positifs if note_globale >= 4 else commentaires_negatifs)
    }
    service_client.append(record)

with (output_dir / 'myfeelback_service_client.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=service_client[0].keys())
    writer.writeheader()
    writer.writerows(service_client)

print("✅ myfeelback_service_client.csv généré")

# ============================================================================
# 5. FEEDBACK APPLICATION MOBILE
# ============================================================================

fonctionnalites = [
    "Consultation de contrats", "Déclaration de sinistre", "Demande d'attestation",
    "Paiement", "Chat avec conseiller", "Gestion de profil",
    "Notification", "Espace documentaire", "Simulation de devis", "Suivi de remboursement"
]

versions_app = ["iOS 2.4.1", "iOS 2.4.0", "iOS 2.3.5", "Android 2.4.1", "Android 2.4.0", "Android 2.3.5"]
types_feedback = ["Bug signalé", "Suggestion d'amélioration", "Appréciation positive", "Difficulté d'utilisation"]

app_mobile = []
for i in range(1, nb_records + 1):
    random_days = random.randint(0, 180)
    date_feedback = start_date + timedelta(days=random_days)
    note_globale = random.choices([1, 2, 3, 4, 5], weights=[10, 15, 25, 30, 20])[0]

    bugs = ["L'application se ferme lors du paiement", "Impossible de télécharger les attestations",
            "Notifications qui ne s'affichent pas", "Problème de connexion récurrent"]
    suggestions = ["Ajouter Touch ID/Face ID", "Améliorer l'ergonomie", "Ajouter mode sombre"]
    appreciations = ["Application très pratique", "Interface claire et intuitive", "Facile à utiliser"]
    difficultes = ["Trop complexe pour déclarer un sinistre", "Menu pas intuitif"]

    type_fb = random.choice(types_feedback)
    if type_fb == "Bug signalé":
        commentaire = random.choice(bugs)
    elif type_fb == "Suggestion d'amélioration":
        commentaire = random.choice(suggestions)
    elif type_fb == "Appréciation positive":
        commentaire = random.choice(appreciations)
    else:
        commentaire = random.choice(difficultes)

    record = {
        "feedback_id": f"APPMOB-{i:05d}",
        "client_id": f"CLI-{random.randint(10000, 99999)}",
        "date_feedback": date_feedback.strftime("%Y-%m-%d %H:%M:%S"),
        "version_app": random.choice(versions_app),
        "fonctionnalite": random.choice(fonctionnalites),
        "type_feedback": type_fb,
        "note_globale": note_globale,
        "note_facilite": max(1, min(5, note_globale + random.randint(-1, 1))),
        "note_design": max(1, min(5, note_globale + random.randint(-1, 1))),
        "note_performance": max(1, min(5, note_globale + random.randint(-1, 1))),
        "commentaire": commentaire
    }
    app_mobile.append(record)

with (output_dir / 'myfeelback_app_mobile.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=app_mobile[0].keys())
    writer.writeheader()
    writer.writerows(app_mobile)

print("✅ myfeelback_app_mobile.csv généré")

# ============================================================================
# 6. FEEDBACK NPS (Net Promoter Score)
# ============================================================================

profils_client = [
    "Client depuis < 1 an", "Client depuis 1-3 ans", "Client depuis 3-5 ans",
    "Client depuis 5-10 ans", "Client depuis > 10 ans"
]

nb_contrats_ranges = ["1 contrat", "2 contrats", "3 contrats", "4+ contrats"]

raisons_detracteurs = [
    "Tarifs trop élevés", "Service client décevant", "Remboursements insuffisants",
    "Trop de complications administratives", "Manque de transparence"
]

raisons_passifs = [
    "Satisfait sans plus", "Prix corrects mais pas les meilleurs",
    "Service correct mais améliorable", "Pas de problème majeur"
]

raisons_promoteurs = [
    "Excellent rapport qualité/prix", "Conseiller toujours disponible et efficace",
    "Remboursements rapides et sans souci", "Confiance totale", "Service client irréprochable"
]

nps_data = []
for i in range(1, nb_records + 1):
    random_days = random.randint(0, 180)
    date_feedback = start_date + timedelta(days=random_days)
    nps_score = random.choices(range(0, 11), weights=[3, 3, 4, 5, 6, 7, 8, 10, 15, 20, 19])[0]

    if nps_score <= 6:
        categorie = "Détracteur"
        raison = random.choice(raisons_detracteurs)
    elif nps_score <= 8:
        categorie = "Passif"
        raison = random.choice(raisons_passifs)
    else:
        categorie = "Promoteur"
        raison = random.choice(raisons_promoteurs)

    record = {
        "feedback_id": f"NPS-{i:05d}",
        "client_id": f"CLI-{random.randint(10000, 99999)}",
        "date_feedback": date_feedback.strftime("%Y-%m-%d"),
        "nps_score": nps_score,
        "categorie": categorie,
        "profil_client": random.choice(profils_client),
        "nb_contrats": random.choice(nb_contrats_ranges),
        "a_eu_sinistre": random.choice(["Oui", "Non"]),
        "a_contacte_service_client": random.choice(["Oui", "Non"]),
        "utilise_app_mobile": random.choice(["Oui", "Non"]),
        "commentaire": raison
    }
    nps_data.append(record)

with (output_dir / 'myfeelback_nps.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=nps_data[0].keys())
    writer.writeheader()
    writer.writerows(nps_data)

print("✅ myfeelback_nps.csv généré")

# ============================================================================
# 7. FEEDBACK AGENCES
# ============================================================================

agences = [
    "Luxembourg-Centre", "Luxembourg-Gare", "Esch-sur-Alzette", "Differdange",
    "Dudelange", "Ettelbruck", "Diekirch", "Wiltz", "Remich", "Grevenmacher"
]

motifs_visite = [
    "Souscription nouveau contrat", "Modification de contrat", "Résiliation",
    "Question/conseil", "Déclaration sinistre", "Réclamation",
    "Rendez-vous conseiller", "Retrait de documents", "Paiement", "Demande d'information"
]

agences_feedback = []
for i in range(1, nb_records + 1):
    random_days = random.randint(0, 180)
    date_feedback = start_date + timedelta(days=random_days)
    note_globale = random.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 40, 32])[0]

    commentaires_positifs = [
        "Accueil chaleureux", "Conseiller très professionnel", "Pas d'attente, service rapide",
        "Agence bien située et accueillante", "Personnel compétent et à l'écoute"
    ]

    commentaires_negatifs = [
        "Temps d'attente excessif", "Agence trop petite, manque de place",
        "Conseiller pressé", "Parking difficile", "Horaires d'ouverture contraignants"
    ]

    record = {
        "feedback_id": f"AGENCE-{i:05d}",
        "client_id": f"CLI-{random.randint(10000, 99999)}",
        "date_feedback": date_feedback.strftime("%Y-%m-%d"),
        "agence": random.choice(agences),
        "motif_visite": random.choice(motifs_visite),
        "avec_rendez_vous": random.choice(["Oui", "Non"]),
        "temps_attente": random.choice(["< 5 min", "5-10 min", "10-15 min", "15-30 min", "> 30 min"]),
        "note_globale": note_globale,
        "note_accueil": max(1, min(5, note_globale + random.randint(-1, 1))),
        "note_competence_conseiller": max(1, min(5, note_globale + random.randint(-1, 1))),
        "note_proprete_locaux": max(1, min(5, note_globale + random.randint(-1, 0))),
        "note_accessibilite": max(1, min(5, note_globale + random.randint(-1, 0))),
        "reviendrait": "Oui" if note_globale >= 4 else ("Non" if note_globale <= 2 else "Peut-être"),
        "commentaire": random.choice(commentaires_positifs if note_globale >= 4 else commentaires_negatifs)
    }
    agences_feedback.append(record)

with (output_dir / 'myfeelback_agences.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=agences_feedback[0].keys())
    writer.writeheader()
    writer.writerows(agences_feedback)

print("✅ myfeelback_agences.csv généré")

# ============================================================================
# STATISTIQUES GLOBALES
# ============================================================================

print("\n" + "="*60)
print("📊 RÉSUMÉ DE GÉNÉRATION")
print("="*60)
print(f"✅ 7 fichiers CSV générés avec {nb_records} enregistrements chacun")
print(f"📅 Période: {start_date.strftime('%Y-%m-%d')} à {datetime.now().strftime('%Y-%m-%d')}")
print("\n📁 Fichiers créés:")
print("   1. tickets_jira.csv - Tickets IT internes")
print("   2. myfeelback_remboursements.csv - Sinistres et remboursements")
print("   3. myfeelback_souscriptions.csv - Feedback après souscription")
print("   4. myfeelback_service_client.csv - Satisfaction service client")
print("   5. myfeelback_app_mobile.csv - Retours application mobile")
print("   6. myfeelback_nps.csv - Net Promoter Score")
print("   7. myfeelback_agences.csv - Satisfaction visites en agence")

# Calcul NPS
detracteurs = sum(1 for r in nps_data if r['categorie'] == 'Détracteur')
promoteurs = sum(1 for r in nps_data if r['categorie'] == 'Promoteur')
nps = ((promoteurs - detracteurs) / len(nps_data)) * 100

print(f"\n📈 NPS Score: {nps:.1f}")
print(f"   - Promoteurs: {promoteurs} ({promoteurs/len(nps_data)*100:.1f}%)")
print(f"   - Passifs: {len(nps_data)-promoteurs-detracteurs} ({(len(nps_data)-promoteurs-detracteurs)/len(nps_data)*100:.1f}%)")
print(f"   - Détracteurs: {detracteurs} ({detracteurs/len(nps_data)*100:.1f}%)")

# Stats moyennes
avg_souscription = sum(r['note_globale'] for r in souscriptions) / len(souscriptions)
avg_service = sum(r['note_globale'] for r in service_client) / len(service_client)
avg_app = sum(r['note_globale'] for r in app_mobile) / len(app_mobile)
avg_agence = sum(r['note_globale'] for r in agences_feedback) / len(agences_feedback)

total_reclame = sum(float(r['montant_reclame']) for r in remboursements)
total_rembourse = sum(float(r['montant_rembourse']) for r in remboursements)

print(f"\n⭐ Notes moyennes:")
print(f"   - Souscriptions: {avg_souscription:.2f}/5")
print(f"   - Service client: {avg_service:.2f}/5")
print(f"   - Application mobile: {avg_app:.2f}/5")
print(f"   - Agences: {avg_agence:.2f}/5")

print(f"\n💰 Remboursements:")
print(f"   - Montant réclamé: {total_reclame:,.2f} €")
print(f"   - Montant remboursé: {total_rembourse:,.2f} €")
print(f"   - Taux de remboursement: {(total_rembourse/total_reclame*100):.1f}%")
print("="*60)
