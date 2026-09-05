import { useState, useRef, useEffect } from 'react';
import { useLanguage } from '../i18n/LanguageContext';

// Per-language content for the BrandAura Guide. `en` is the source of truth;
// any language without a full block gracefully falls back to English, which
// matches the app-wide i18n behaviour.
const LANG_CONTENT = {
  en: {
    welcome: 'Hi! 👋 I’m your BrandAura expert guide. Ask me anything about the platform — connecting accounts, media, scheduling, or fixing errors.',
    fallback: 'Thank you for your question. I’m the BrandAura onboarding guide and I can help with connecting accounts, cropping and uploading media, auto-scheduling, content generation, and fixing Meta or LinkedIn errors. Please rephrase your question around one of those topics.',
    developedBy: 'BrandAura was developed by Maria Shafqat, CEO of Meveryx, in collaboration with co-founder Zahra Imran.',
    quick: {
      connect: '🔗 How do I connect Instagram/Facebook/LinkedIn?',
      media: '🖼️ How do I crop & upload media?',
      schedule: '⏰ How does auto-publishing work?',
      trouble: '🚑 Why is my Facebook publish failing?',
    },
    kb: {
      connect: {
        keywords: ['connect', 'connection', 'link', 'instagram', 'facebook', 'linkedin', 'account', 'social'],
        lines: [
          'Open the Dashboard and go to the "Social accounts" section.',
          'Click "Connect" for the platform you want. Instagram connects through Facebook Login.',
          'Approve the permissions in the secure authorization window, then you return to the dashboard and the account turns green.',
          'Tip: to publish to Facebook Pages you must manage at least one Page, and Instagram must be a Professional account linked to that Page. If pages stay hidden, the Meta App usually needs to be in Live mode with you added as a tester.',
        ],
      },
      media: {
        keywords: ['crop', 'upload', 'media', 'image', 'photo', 'video', 'attach', 'file', 'add image'],
        lines: [
          'After generating content, go to the "Media" section below the AI image tools.',
          'Click "Browse files" and choose an image — the crop tool opens automatically. Adjust the frame and press Apply.',
          'Videos are attached directly and preview inline.',
          'Files are only uploaded when you click Publish. Your media and drafts persist across pages; use "Remove" or "Clear all" to delete them.',
        ],
      },
      schedule: {
        keywords: ['schedule', 'scheduler', 'auto', 'autopilot', 'best time', 'plan', 'bulk', 'auto-schedule'],
        lines: [
          'Open "Auto Scheduler" from the Dashboard or visit the Scheduler page.',
          'Write or paste a caption, optionally attach media, pick the platforms, and choose a cadence or best-time window.',
          'BrandAura can also bulk-plan multiple posts across dates.',
          'The scheduler runs 24/7 in the background and auto-publishes at the chosen times. Track everything in the Calendar and History pages.',
        ],
      },
      trouble: {
        keywords: ['trouble', 'error', 'fail', 'meta', 'instagram', 'linkedin', 'bug', 'issue', 'not working', 'reason', 'token'],
        lines: [
          'Facebook/Instagram publish failures usually fall into two buckets.',
          '① Token errors ("No Facebook Pages found", OAuth 190) mean the Facebook session was invalidated or the Page list is empty — reconnect the account from the Dashboard and verify the FB App is Live with you as a tester.',
          '② Page access errors ((#200) permission) mean that Page is not managed by the connected account — add your profile in the Facebook Page settings → Page access.',
          'LinkedIn errors usually mean the account needs reconnecting so BrandAura can read your real profile. After any change, reconnect and publish again.',
        ],
      },
      generate: {
        keywords: ['generate', 'content', 'post', 'caption', 'ai', 'write', 'draft', 'studio', 'create'],
        lines: [
          'Open Content Studio on the Dashboard — enter a Topic, pick a Tone & Style and the target Platforms, then click Generate Content.',
          'The AI writes one publish-ready post. You can also run a Market & Competitor scan to refine it.',
          'Add an AI image, crop or attach your own media, then click Publish.',
          'Your topic, post, image prompt and media stay saved as you move between pages.',
        ],
      },
      identity: {
        keywords: ['who developed', 'who made', 'who created', 'who built', 'developer', 'founder', 'maker', 'created brandaura', 'made brandaura'],
        lines: ['BrandAura was developed by Maria Shafqat, CEO of Meveryx, in collaboration with co-founder Zahra Imran.'],
      },
    },
  },
  es: {
    welcome: '¡Hola! 👋 Soy tu guía experto de BrandAura. Pregúntame lo que quieras sobre la plataforma: conectar cuentas, medios, programación o resolver errores.',
    fallback: 'Gracias por tu pregunta. Soy el guía de introducción de BrandAura y puedo ayudarte a conectar cuentas, recortar y subir medios, programar publicaciones automáticas, generar contenido y solucionar errores de Meta o LinkedIn. Por favor, reformula tu pregunta en torno a uno de esos temas.',
    developedBy: 'BrandAura fue desarrollado por Maria Shafqat, CEO de Meveryx, en colaboración con la cofundadora Zahra Imran.',
    quick: {
      connect: '🔗 ¿Cómo conecto Instagram/Facebook/LinkedIn?',
      media: '🖼️ ¿Cómo recorto y subo imágenes o videos?',
      schedule: '⏰ ¿Cómo funciona la publicación automática?',
      trouble: '🚑 ¿Por qué falla la publicación en Facebook?',
    },
    kb: {
      connect: {
        keywords: ['conectar', 'conexión', 'conexion', 'vincular', 'instagram', 'facebook', 'linkedin', 'cuenta', 'social'],
        lines: [
          'Abre el Panel de control y ve a la sección "Cuentas sociales".',
          'Haz clic en "Conectar" para la plataforma que quieras. Instagram se conecta mediante el inicio de sesión de Facebook.',
          'Aprueba los permisos en la ventana segura y volverás al panel con la cuenta en verde.',
          'Consejo: para publicar en páginas de Facebook debes administrar al menos una página, e Instagram debe ser una cuenta Profesional vinculada a esa página. Si las páginas no aparecen, la app de Meta suele necesitar estar en modo Live y añadirte como tester.',
        ],
      },
      media: {
        keywords: ['recortar', 'recorte', 'subir', 'imagen', 'foto', 'video', 'adjuntar', 'archivo', 'media'],
        lines: [
          'Tras generar contenido, ve a la sección "Medios", debajo de las herramientas de imagen IA.',
          'Haz clic en "Examinar archivos" y elige una imagen: la herramienta de recorte se abre sola. Ajusta el marco y pulsa Aplicar.',
          'Los videos se adjuntan directamente y se previsualizan.',
          'Los archivos solo se suben cuando pulsas Publicar. Tus medios y borradores se guardan entre páginas; usa "Quitar" o "Borrar todo" para eliminarlos.',
        ],
      },
      schedule: {
        keywords: ['programar', 'horario', 'automático', 'automatico', 'mejor hora', 'planificar', 'lote', 'auto'],
        lines: [
          'Abre "Programador automático" desde el Panel de control o ve a la página del Programador.',
          'Escribe o pega un texto, añade medios si quieres, elige las plataformas y selecciona una cadencia o la mejor franja horaria.',
          'BrandAura también puede planificar varias publicaciones en fechas distintas.',
          'El programador funciona 24/7 en segundo plano y publica automáticamente. Haz seguimiento en Calendario e Historial.',
        ],
      },
      trouble: {
        keywords: ['error', 'falla', 'fallo', 'no funciona', 'meta', 'instagram', 'linkedin', 'problema', 'token'],
        lines: [
          'Los fallos de publicación en Facebook/Instagram suelen tener dos causas.',
          '① Errores de token ("No se encontraron páginas de Facebook", OAuth 190) significan que la sesión se invalidó o la lista de páginas está vacía: reconecta la cuenta y verifica que la app esté en modo Live con tu usuario como tester.',
          '② Errores de acceso a la página ((#200) permiso) significan que esa página no está gestionada por la cuenta conectada: añade tu perfil en Configuración de la página → Acceso a la página.',
          'Los errores de LinkedIn suelen requerir reconectar la cuenta para leer tu perfil real. Después de cualquier cambio, reconecta y publica de nuevo.',
        ],
      },
      generate: {
        keywords: ['generar', 'contenido', 'publicación', 'captura', 'ia', 'escribir', 'borrador', 'crear'],
        lines: [
          'Abre Content Studio en el Panel de control: introduce un Tema, elige un Tono y estilo y las Plataformas, luego pulsa Generar contenido.',
          'La IA escribe una publicación lista para publicar. También puedes ejecutar un análisis de mercado para mejorarla.',
          'Añade una imagen IA, recorta o adjunta tu propio medio y pulsa Publicar.',
          'Tu tema, publicación, prompt de imagen y medios se guardan al cambiar de página.',
        ],
      },
      identity: {
        keywords: ['quién desarrolló', 'quien desarrollo', 'quién creó', 'quien creo', 'quién hizo', 'desarrollador', 'fundador', 'creador'],
        lines: ['BrandAura fue desarrollado por Maria Shafqat, CEO de Meveryx, en colaboración con la cofundadora Zahra Imran.'],
      },
    },
  },
  fr: {
    welcome: 'Bonjour ! 👋 Je suis votre guide expert BrandAura. Posez-moi toutes vos questions sur la plateforme : connexion des comptes, médias, planification ou résolution d’erreurs.',
    fallback: 'Merci pour votre question. Je suis le guide de prise en main de BrandAura et je peux vous aider à connecter des comptes, recadrer et téléverser des médias, planifier des publications automatiques, générer du contenu et résoudre les erreurs Meta ou LinkedIn. Merci de reformuler votre question autour de l’un de ces sujets.',
    developedBy: 'BrandAura a été développé par Maria Shafqat, PDG de Meveryx, en collaboration avec la cofondatrice Zahra Imran.',
    quick: {
      connect: '🔗 Comment connecter Instagram/Facebook/LinkedIn ?',
      media: '🖼️ Comment recadrer et téléverser des médias ?',
      schedule: '⏰ Comment fonctionne la publication automatique ?',
      trouble: '🚑 Pourquoi ma publication Facebook échoue-t-elle ?',
    },
    kb: {
      connect: {
        keywords: ['connecter', 'connexion', 'lier', 'instagram', 'facebook', 'linkedin', 'compte', 'réseau', 'social'],
        lines: [
          'Ouvrez le Tableau de bord et allez dans la section « Comptes sociaux ».',
          'Cliquez sur « Connecter » pour la plateforme souhaitée. Instagram se connecte via Facebook Login.',
          'Approuvez les autorisations dans la fenêtre sécurisée, puis vous revenez au tableau de bord avec le compte en vert.',
          'Astuce : pour publier sur des Pages Facebook, vous devez gérer au moins une Page, et Instagram doit être un compte Professionnel lié à cette Page. Si les pages restent invisibles, l’app Meta doit généralement être en mode Live avec vous ajouté comme testeur.',
        ],
      },
      media: {
        keywords: ['recadrer', 'recadrage', 'téléverser', 'upload', 'média', 'image', 'photo', 'vidéo', 'joindre', 'fichier'],
        lines: [
          'Après avoir généré du contenu, allez dans la section « Médias », sous les outils d’image IA.',
          'Cliquez sur « Parcourir » et choisissez une image : l’outil de recadrage s’ouvre automatiquement. Ajustez le cadre et appuyez sur Appliquer.',
          'Les vidéos sont jointes directement et apparaissent en aperçu.',
          'Les fichiers ne sont envoyés qu’au clic sur Publier. Vos médias et brouillons sont conservés entre les pages ; utilisez « Retirer » ou « Tout effacer » pour les supprimer.',
        ],
      },
      schedule: {
        keywords: ['planifier', 'programmer', 'planification', 'automatique', 'meilleur moment', 'publication'],
        lines: [
          'Ouvrez « Planificateur automatique » depuis le Tableau de bord ou la page Planificateur.',
          'Écrivez ou collez un texte, joignez éventuellement un média, choisissez les plateformes et une cadence ou un créneau horaire optimal.',
          'BrandAura peut aussi planifier plusieurs publications sur différentes dates.',
          'Le planificateur tourne 24h/24 en arrière-plan et publie automatiquement. Suivez tout dans le Calendrier et l’Historique.',
        ],
      },
      trouble: {
        keywords: ['erreur', 'échec', 'problème', 'ne fonctionne pas', 'meta', 'instagram', 'linkedin', 'token'],
        lines: [
          'Les échecs de publication Facebook/Instagram relèvent généralement de deux causes.',
          '① Erreurs de jeton (« Aucune Page Facebook trouvée », OAuth 190) : la session a été invalidée ou la liste de Pages est vide — reconnectez le compte et vérifiez que l’app FB est en mode Live avec vous comme testeur.',
          '② Erreurs d’accès à la Page ((#200) permission) : cette Page n’est pas gérée par le compte connecté — ajoutez votre profil dans Paramètres de la Page → Accès à la Page.',
          'Les erreurs LinkedIn indiquent généralement qu’il faut reconnecter le compte pour lire votre profil réel. Après tout changement, reconnectez et republiez.',
        ],
      },
      generate: {
        keywords: ['générer', 'contenu', 'publication', 'légende', 'ia', 'écrire', 'brouillon', 'créer'],
        lines: [
          'Ouvrez Content Studio depuis le Tableau de bord — saisissez un Sujet, choisissez un Ton et un style et les Plateformes, puis cliquez sur Générer le contenu.',
          'L’IA rédige une publication prête à publier. Vous pouvez aussi lancer une analyse de marché pour l’affiner.',
          'Ajoutez une image IA, recadrez ou joignez votre propre média, puis publiez.',
          'Votre sujet, votre publication, le prompt d’image et vos médias sont conservés d’une page à l’autre.',
        ],
      },
      identity: {
        keywords: ['qui a développé', 'qui a créé', 'qui a fait', 'développeur', 'créateur', 'fondateur'],
        lines: ['BrandAura a été développé par Maria Shafqat, PDG de Meveryx, en collaboration avec la cofondatrice Zahra Imran.'],
      },
    },
  },
  de: {
    welcome: 'Hallo! 👋 Ich bin Ihr BrandAura-Experten-Guide. Fragen Sie mich alles zur Plattform: Konten verbinden, Medien, Planung oder Fehlerbehebung.',
    fallback: 'Vielen Dank für Ihre Frage. Ich bin der Einführungs-Guide von BrandAura und kann Ihnen beim Verbinden von Konten, Zuschneiden und Hochladen von Medien, automatischer Planung, Content-Erstellung und bei Meta- oder LinkedIn-Fehlern helfen. Bitte formulieren Sie Ihre Frage zu einem dieser Themen neu.',
    developedBy: 'BrandAura wurde von Maria Shafqat, CEO von Meveryx, in Zusammenarbeit mit Mitgründerin Zahra Imran entwickelt.',
    quick: {
      connect: '🔗 Wie verbinde ich Instagram/Facebook/LinkedIn?',
      media: '🖼️ Wie schneide ich Medien zu und lade sie hoch?',
      schedule: '⏰ Wie funktioniert die automatische Veröffentlichung?',
      trouble: '🚑 Warum schlägt meine Facebook-Veröffentlichung fehl?',
    },
    kb: {
      connect: {
        keywords: ['verbinden', 'verbindung', 'verknüpfen', 'instagram', 'facebook', 'linkedin', 'konto', 'sozial'],
        lines: [
          'Öffnen Sie das Dashboard und gehen Sie zum Bereich „Soziale Konten“.',
          'Klicken Sie auf „Verbinden“ für die gewünschte Plattform. Instagram verbindet sich über den Facebook-Login.',
          'Bestätigen Sie die Berechtigungen im sicheren Fenster – dann kehren Sie zum Dashboard zurück und das Konto wird grün.',
          'Tipp: Für Facebook-Seiten müssen Sie mindestens eine Seite verwalten, und Instagram muss ein professionelles, mit dieser Seite verknüpftes Konto sein. Wenn keine Seiten angezeigt werden, muss die Meta-App meist im Live-Modus sein und Sie als Tester hinzugefügt werden.',
        ],
      },
      media: {
        keywords: ['zuschneiden', 'crop', 'hochladen', 'bild', 'foto', 'video', 'anhängen', 'datei', 'medien'],
        lines: [
          'Gehen Sie nach der Content-Erstellung zum Bereich „Medien“ unter den KI-Bildtools.',
          'Klicken Sie auf „Durchsuchen“ und wählen Sie ein Bild – das Zuschneidewerkzeug öffnet sich automatisch. Passen Sie den Rahmen an und drücken Sie Übernehmen.',
          'Videos werden direkt angehängt und inline vorschau.',
          'Dateien werden nur beim Klick auf Veröffentlichen hochgeladen. Ihre Medien und Entwürfe bleiben über Seiten hinweg erhalten; „Entfernen“ oder „Alles löschen“ entfernt sie.',
        ],
      },
      schedule: {
        keywords: ['planen', 'zeitplan', 'termin', 'automatisch', 'beste zeit', 'publizieren', 'einplanen'],
        lines: [
          'Öffnen Sie „Autoplaner“ im Dashboard oder besuchen Sie die Planer-Seite.',
          'Schreiben Sie einen Text, hängen Sie optional Medien an, wählen Sie Plattformen und eine Kadenz oder ein Zeitfenster.',
          'BrandAura kann auch mehrere Beiträge über mehrere Daten planen.',
          'Der Planer läuft rund um die Uhr und veröffentlicht automatisch. Verfolgen Sie alles im Kalender und im Verlauf.',
        ],
      },
      trouble: {
        keywords: ['fehler', 'problem', 'funktioniert nicht', 'meta', 'instagram', 'linkedin', 'token'],
        lines: [
          'Veröffentlichungsfehler bei Facebook/Instagram haben meist zwei Ursachen.',
          '① Token-Fehler („Keine Facebook-Seiten gefunden“, OAuth 190) bedeuten, dass die Sitzung ungültig wurde oder die Seitenliste leer ist – verbinden Sie das Konto neu und prüfen Sie, ob die FB-App im Live-Modus ist und Sie Tester sind.',
          '② Seitenzugriffsfehler ((#200) Berechtigung) bedeuten, dass die Seite nicht vom verbundenen Konto verwaltet wird – fügen Sie Ihr Profil in den Seiten-Einstellungen → Seitenzugriff hinzu.',
          'LinkedIn-Fehler bedeuten meist, dass das Konto neu verbunden werden muss. Verbinden Sie nach jeder Änderung neu und veröffentlichen Sie erneut.',
        ],
      },
      generate: {
        keywords: ['generieren', 'erstellen', 'inhalt', 'beitrag', 'überschrift', 'ki', 'schreiben', 'text'],
        lines: [
          'Öffnen Sie das Content Studio im Dashboard – Thema eingeben, Ton & Stil und Plattformen wählen, dann auf „Content generieren“ klicken.',
          'Die KI schreibt einen veröffentlichungsfertigen Beitrag. Sie können auch einen Markt-Scan zur Verfeinerung starten.',
          'Fügen Sie ein KI-Bild hinzu, schneiden Sie Medien zu oder hängen Sie eigene an, dann veröffentlichen.',
          'Thema, Beitrag, Bild-Prompt und Medien bleiben beim Wechsel zwischen Seiten erhalten.',
        ],
      },
      identity: {
        keywords: ['wer hat entwickelt', 'wer hat erstellt', 'wer hat gebaut', 'entwickelt', 'ersteller', 'gründer', 'gründerin'],
        lines: ['BrandAura wurde von Maria Shafqat, CEO von Meveryx, in Zusammenarbeit mit Mitgründerin Zahra Imran entwickelt.'],
      },
    },
  },
  ar: {
    welcome: 'مرحبًا! 👋 أنا مرشدك الخبير في براند أورا. اسألني عن أي شيء في المنصة — ربط الحسابات والوسائط والجدولة أو حل الأخطاء.',
    fallback: 'شكرًا لسؤالك. أنا مرشد براند أورا ويمكنني مساعدتك في ربط الحسابات وقص ورفع الوسائط والجدولة التلقائية وتوليد المحتوى وحل أخطاء ميتا أو لينكد إن. يرجى إعادة صياغة سؤالك حول أحد هذه المواضيع.',
    developedBy: 'تم تطوير براند أورا بواسطة ماريا شفقت، الرئيسة التنفيذية لشركة ميفركس، بالتعاون مع المؤسِّسة المشاركة زهراء عمران.',
    quick: {
      connect: '🔗 كيف أربط إنستغرام/فيسبوك/لينكد إن؟',
      media: '🖼️ كيف أقوم بقص الصور ورفع الوسائط؟',
      schedule: '⏰ كيف تعمل الجدولة التلقائية؟',
      trouble: '🚑 لماذا يفشل النشر على فيسبوك؟',
    },
    kb: {
      connect: {
        keywords: ['توصيل', 'ربط', 'انستغرام', 'فيسبوك', 'لينكد إن', 'حساب', 'تواصل'],
        lines: [
          'افتح لوحة التحكم وانتقل إلى قسم «الحسابات الاجتماعية».',
          'انقر «ربط» للمنصة المطلوبة. يتصل إنستغرام عبر تسجيل دخول فيسبوك.',
          'وافق على الأذونات في النافذة الآمنة، وستعود إلى لوحة التحكم والحساب أخضر.',
          'نصيحة: للنشر على صفحات فيسبوك يجب إدارة صفحة واحدة على الأقل، ويجب أن يكون إنستغرام حسابًا احترافيًا مرتبطًا بها. إذا لم تظهر الصفحات، يجب أن يكون تطبيق ميتا في وضع Live مع إضافتك كمختبر.',
        ],
      },
      media: {
        keywords: ['قص', 'قص الصورة', 'رفع', 'صورة', 'فيديو', 'مرفق', 'ملف', 'وسائط'],
        lines: [
          'بعد توليد المحتوى، انتقل إلى قسم «الوسائط» أسفل أدوات الصور بالذكاء الاصطناعي.',
          'انقر «تصفح الملفات» واختر صورة — ستفتح أداة القص تلقائيًا. اضبط الإطار واضغط تطبيق.',
          'تُرفق الفيديوهات مباشرة وتظهر في المعاينة.',
          'تُرفع الملفات فقط عند النقر على نشر. تُحفظ وسائطك ومسوداتك بين الصفحات؛ استخدم «إزالة» أو «مسح الكل» لحذفها.',
        ],
      },
      schedule: {
        keywords: ['جدولة', 'جدول', 'تلقائي', 'أفضل وقت', 'نشر', 'خطة'],
        lines: [
          'افتح «الجدولة التلقائية» من لوحة التحكم أو صفحة الجدول.',
          'اكتب أو الصق نصًا، وأرفق وسائل اختياريًا، واختر المنصات والإيقاع أو أفضل وقت.',
          'يمكن لبراند أورا أيضًا تخطيط عدة منشورات عبر تواريخ مختلفة.',
          'يعمل الجدول على مدار الساعة وينشر تلقائيًا. تابع كل شيء في التقويم والسجل.',
        ],
      },
      trouble: {
        keywords: ['خطأ', 'فشل', 'مشكلة', 'لا يعمل', 'توكن', 'ميتا', 'رمز'],
        lines: [
          'أخطاء نشر فيسبوك/إنستغرام تنقسم عادة إلى مجموعتين.',
          '① أخطاء الرمز («لم يتم العثور على صفحات فيسبوك»، OAuth 190) تعني إبطال الجلسة أو أن قائمة الصفحات فارغة — أعد ربط الحساب وتأكد من أن التطبيق في وضع Live.',
          '② أخطاء الوصول إلى الصفحة (الترخيص #200) تعني أن الصفحة غير مُدارة من الحساب المتصل — أضف ملفك في إعدادات الصفحة → وصول إلى الصفحة.',
          'أخطاء لينكد إن تعني عادة إعادة ربط الحساب لقراءة ملفك الحقيقي. بعد أي تغيير، أعد الربط ثم انشر.',
        ],
      },
      generate: {
        keywords: ['توليد', 'إنشاء', 'محتوى', 'منشور', 'ذكاء اصطناعي', 'كتابة'],
        lines: [
          'افتح الاستوديو من لوحة التحكم — أدخل الموضوع واختر النغمة والأسلوب والمنصات ثم انقر «توليد المحتوى».',
          'تكتب الذكاء الاصطناعي منشورًا جاهزًا للنشر. يمكنك أيضًا تشغيل تحليل السوق لتحسينه.',
          'أضف صورة ذكاء اصطناعي أو قصّ وسائط أو ارِفق وسائطك الخاصة ثم انشر.',
          'يُحفظ موضوعك ومنشورك ونص الصورة والوسائط عند التنقل بين الصفحات.',
        ],
      },
      identity: {
        keywords: ['من طور', 'من صنع', 'من أنشأ', 'مطور', 'مؤسس', 'منشئ'],
        lines: ['تم تطوير براند أورا بواسطة ماريا شفقت، الرئيسة التنفيذية لشركة ميفركس، بالتعاون مع المؤسِّسة المشاركة زهراء عمران.'],
      },
    },
  },
  ur: {
    welcome: 'ہیلو! 👋 میں آپ کا برینڈ آورا ماہر گائیڈ ہوں۔ پلیٹ فارم کے بارے میں کچھ بھی پوچھیں — اکاؤنٹس جوڑنا، میڈیا، شیڈولنگ یا خرابیوں کا حل۔',
    fallback: 'آپ کے سوال کا شکریہ۔ میں برینڈ آورا کا گائیڈ ہوں اور اکاؤنٹ جوڑنے، میڈیا کروپ اور اپ لوڈ، خودکار شیڈولنگ، مواد بنانے اور میٹا یا لنکڈ ان کی خرابیاں حل کرنے میں مدد کر سکتا ہوں۔ براہ کرم اپنا سوال انہی موضوعات میں سے کسی پر دہرائیں۔',
    developedBy: 'برینڈ آورا کو ماریہ شفقت، می ویرکس کی سی ای او، اور شریک بانی زہرہ عمران کے اشتراک سے تیار کیا گیا ہے۔',
    quick: {
      connect: '🔗 انسٹاگرام/فیس بک/لنکڈ ان کیسے جوڑیں؟',
      media: '🖼️ میڈیا کروپ اور اپ لوڈ کیسے کریں؟',
      schedule: '⏰ خودکار اشاعت کیسے کام کرتی ہے؟',
      trouble: '🚑 فیس بک پر اشاعت کیوں ناکام ہو رہی ہے؟',
    },
    kb: {
      connect: {
        keywords: ['منسلک', 'کنیکٹ', 'انسٹاگرام', 'فیس بک', 'لنکڈ ان', 'اکاؤنٹ', 'سماجی'],
        lines: [
          'ڈیش بورڈ کھولیں اور «سماجی اکاؤنٹس» والے حصے میں جائیں۔',
          'جس پلیٹ فارم کو جوڑنا ہے اس کے لیے «کنیکٹ» دبائیں۔ انسٹاگرام فیس بک لاگ ان سے جڑتا ہے۔',
          'محفوظ ونڈو میں اجازتیں منظور کریں، پھر ڈیش بورڈ پر واپس آئیں اور اکاؤنٹ سبز ہو جائے گا۔',
          'مشورہ: فیس بک پیجز پر پوسٹ کرنے کے لیے کم از کم ایک پیج منظم کریں، اور انسٹاگرام اسی پیج سے منسلک پیشہ ورانہ اکاؤنٹ ہونا چاہیے۔ اگر پیجز نظر نہ آئیں تو میٹا ایپ عموماً Live موڈ میں ہونی چاہیے اور آپ کو بطور ٹیسٹر شامل کیا جانا چاہیے۔',
        ],
      },
      media: {
        keywords: ['کروپ', 'کٹائی', 'اپ لوڈ', 'امیج', 'تصویر', 'وڈیو', 'منسلک', 'فائل'],
        lines: [
          'مواد بنانے کے بعد «میڈیا» والے حصے میں جائیں جو AI امیج ٹولز کے نیچے ہے۔',
          '«فائلیں دیکھیں» دبائیں اور تصویر چنیں — کروپ ٹول خود کھل جاتا ہے۔ فریم ترتیب دے کر Apply دبائیں۔',
          'وڈیوز براہ راست منسلک ہوتی ہیں اور جھلک میں نظر آتی ہیں۔',
          'فائلیں صرف Publish دبانے پر اپ لوڈ ہوتی ہیں۔ آپ کے میڈیا اور مسودات صفحات کے درمیان محفوظ رہتے ہیں؛ حذف کیلئے «Remove» یا «Clear all» استعمال کریں۔',
        ],
      },
      schedule: {
        keywords: ['شیڈول', 'شیڈیولر', 'خودکار', 'بہترین وقت', 'پلان', 'منصوبہ'],
        lines: [
          'ڈیش بورڈ سے «آٹو شیڈیولر» کھولیں یا شیڈیولر صفحہ دیکھیں۔',
          'کیپشن لکھیں یا پیسٹ کریں، اختیاری میڈیا منسلک کریں، پلیٹ فارمز اور رفتار یا بہترین وقت منتخب کریں۔',
          'برینڈ آورا کئی پوسٹس کو مختلف تاریخوں پر بھی پلان کر سکتا ہے۔',
          'شیڈیولر چوبیس گھنٹے پس منظر میں چلتا ہے اور خودکار نشر کرتا ہے۔ سب کچھ کلینڈر اور ہسٹری میں دیکھیں۔',
        ],
      },
      trouble: {
        keywords: ['خرابی', 'غلطی', 'مسئلہ', 'کام نہیں کر', 'ٹوکن', 'میٹا'],
        lines: [
          'فیس بک/انسٹاگرام کی اشاعت کی ناکامیاں عموماً دو قسم کی ہوتی ہیں۔',
          '① ٹوکن کی خرابیاں («کوئی فیس بک پیج نہیں ملا»، OAuth 190) کا مطلب ہے سیشن ختم یا پیج فہرست خالی — اکاؤنٹ دوبارہ جوڑیں اور یقینی بنائیں کہ ایپ Live موڈ میں ہے۔',
          '② پیج تک رسائی کی خرابیاں (اجازت #200) کا مطلب ہے پیج منسلک اکاؤنٹ سے منظم نہیں — پیج سیٹنگز میں اپنا پروفائل شامل کریں۔',
          'لنکڈ ان کی خرابیاں عموماً اکاؤنٹ دوبارہ جوڑنے کی مانگتی ہیں۔ کسی بھی تبدیلی کے بعد دوبارہ جوڑ کر نشر کریں۔',
        ],
      },
      generate: {
        keywords: ['جنریٹ', 'بنائیں', 'محتوی', 'پوسٹ', 'اے آئی', 'لکھیں'],
        lines: [
          'ڈیش بورڈ کا کنٹینٹ اسٹوڈیو کھولیں — موضوع درج کریں، انداز اور پلیٹ فارمز چنیں اور «محتوی بنائیں» دبائیں۔',
          'AI ایک شائع ہونے کے لائق پوسٹ لکھتا ہے۔ بہتر بنانے کے لیے مارکیٹ اسکین بھی چلا سکتے ہیں۔',
          'AI امیج شامل کریں، اپنا میڈیا کروپ کریں یا منسلک کریں، پھر Publish دبائیں۔',
          'آپ کا موضوع، پوسٹ، امیج پرامپٹ اور میڈیا صفحات کے درمیان محفوظ رہتے ہیں۔',
        ],
      },
      identity: {
        keywords: ['کس نے بنایا', 'کس نے تیار کیا', 'بانی', 'ڈویلپر', 'بنانے والا'],
        lines: ['برینڈ آورا کو ماریہ شفقت، می ویرکس کی سی ای او، اور شریک بانی زہرہ عمران کے اشتراک سے تیار کیا گیا ہے۔'],
      },
    },
  },
  hi: {
    welcome: 'नमस्ते! 👋 मैं BrandAura का विशेषज्ञ गाइड हूँ। प्लेटफ़ॉर्म के बारे में कुछ भी पूछें — अकाउंट कनेक्ट करना, मीडिया, शेड्यूलिंग या त्रुटियाँ ठीक करना।',
    fallback: 'आपके प्रश्न के लिए धन्यवाद। मैं BrandAura का ऑनबोर्डिंग गाइड हूँ और अकाउंट कनेक्ट करने, मीडिया क्रॉप व अपलोड करने, ऑटो-शेड्यूलिंग, कंटेंट बनाने और Meta या LinkedIn की त्रुटियाँ सुलझाने में मदद कर सकता हूँ। कृपया अपना प्रश्न इनमें से किसी विषय पर दोबारा पूछें।',
    developedBy: 'BrandAura को मारिया शफ्कत (Meveryx की CEO) और सह-संस्थापक ज़हरा इमरान के सहयोग से विकसित किया गया है।',
    quick: {
      connect: '🔗 Instagram/Facebook/LinkedIn कैसे कनेक्ट करें?',
      media: '🖼️ मीडिया क्रॉप और अपलोड कैसे करें?',
      schedule: '⏰ ऑटो-पब्लिशिंग कैसे काम करती है?',
      trouble: '🚑 मेरी Facebook पोस्ट क्यों फेल हो रही है?',
    },
    kb: {
      connect: {
        keywords: ['कनेक्ट', 'जोड़ें', 'लिंक', 'इंस्टाग्राम', 'फेसबुक', 'लिंक्डइन', 'खाता', 'सोशल'],
        lines: [
          'Dashboard खोलें और «Social accounts» सेक्शन में जाएँ।',
          'जिस प्लेटफ़ॉर्म को जोड़ना है उसके लिए «Connect» दबाएँ। Instagram Facebook Login के ज़रिए जुड़ता है।',
          'सुरक्षित विंडो में अनुमतियाँ मंज़ूर करें, फिर डैशबोर्ड पर वापस आएँ और अकाउंट हरा हो जाएगा।',
          'सुझाव: Facebook Pages पर पोस्ट करने के लिए कम से कम एक Page प्रबंधित करें, और Instagram वही Professional अकाउंट होना चाहिए जो उस Page से जुड़ा हो। अगर pages नहीं दिखते, तो Meta App को Live mode में होना चाहिए और आपको tester के रूप में जोड़ा जाना चाहिए।',
        ],
      },
      media: {
        keywords: ['क्रॉप', 'काटें', 'अपलोड', 'छवि', 'फोटो', 'वीडियो', 'संलग्न', 'फ़ाइल'],
        lines: [
          'कंटेंट बनाने के बाद AI इमेज टूल्स के नीचे «Media» सेक्शन में जाएँ।',
          '«Browse files» दबाएँ और एक इमेज चुनें — क्रॉप टूल अपने आप खुलता है। फ़्रेम सेट करके Apply दबाएँ।',
          'वीडियो सीधे जुड़ते हैं और इनलाइन प्रीव्यू दिखते हैं।',
          'फ़ाइलें केवल Publish दबाने पर अपलोड होती हैं। आपका मीडिया और ड्राफ्ट पेजों के बीच सुरक्षित रहते हैं; हटाने के लिए «Remove» या «Clear all» दबाएँ।',
        ],
      },
      schedule: {
        keywords: ['शेड्यूल', 'ऑटो', 'स्वचालित', 'सबसे अच्छा समय', 'योजना', 'प्रकाशन'],
        lines: [
          'Dashboard से «Auto Scheduler» खोलें या Scheduler पेज पर जाएँ।',
          'कैप्शन लिखें या पेस्ट करें, वैकल्पिक मीडिया जोड़ें, प्लेटफ़ॉर्म चुनें और कैडेंस या बेस्ट-टाइम विंडो चुनें।',
          'BrandAura कई पोस्ट्स को अलग-अलग तारीखों पर भी प्लान कर सकता है।',
          'शेड्यूलर 24/7 बैकग्राउंड में चलता है और चुने हुए समय पर ऑटो-पब्लिश करता है। Calendar और History में सब ट्रैक करें।',
        ],
      },
      trouble: {
        keywords: ['त्रुटि', 'गलती', 'समस्या', 'काम नहीं', 'टोकन', 'मेटा'],
        lines: [
          'Facebook/Instagram पब्लिश की असफलताएँ आम तौर पर दो तरह की होती हैं।',
          '① टोकन त्रुटि («कोई Facebook Page नहीं मिला», OAuth 190) का मतलब है सत्र अमान्य हो गया या Page सूची खाली है — अकाउंट फिर से कनेक्ट करें और पक्का करें कि App Live mode में है।',
          '② Page एक्सेस त्रुटि (अनुमति #200) का मतलब है कि Page जुड़े अकाउंट से प्रबंधित नहीं है — Page settings → Page access में अपना प्रोफ़ाइल जोड़ें।',
          'LinkedIn त्रुटियाँ आमतौर पर अकाउंट दोबारा कनेक्ट करने की माँग करती हैं। किसी भी बदलाव के बाद दोबारा कनेक्ट करके पब्लिश करें।',
        ],
      },
      generate: {
        keywords: ['जनरेट', 'बनाएँ', 'सामग्री', 'पोस्ट', 'कैप्शन', 'एआई', 'लिखें'],
        lines: [
          'Dashboard पर Content Studio खोलें — टॉपिक डालें, Tone & Style और प्लेटफ़ॉर्म चुनें, फिर Generate Content दबाएँ।',
          'AI एक पब्लिश-रेडी पोस्ट लिखता है। उसे बेहतर बनाने के लिए Market & Competitor स्कैन भी चला सकते हैं।',
          'AI इमेज जोड़ें, अपना मीडिया क्रॉप या अटैच करें, फिर Publish दबाएँ।',
          'आपका टॉपिक, पोस्ट, इमेज प्रॉम्प्ट और मीडिया पेजों के बीच सेव रहते हैं।',
        ],
      },
      identity: {
        keywords: ['किसने बनाया', 'किसने विकसित', 'डेवलपर', 'संस्थापक', 'निर्माता'],
        lines: ['BrandAura को मारिया शफ्कत (Meveryx की CEO) और सह-संस्थापक ज़हरा इमरान के सहयोग से विकसित किया गया है।'],
      },
    },
  },
};

// Best-effort BCP-47 voice tags per app language code.
const VOICE_BY_LANG = {
  en: 'en-US', es: 'es-ES', fr: 'fr-FR', de: 'de-DE', ar: 'ar-SA', ur: 'ur-PK', hi: 'hi-IN',
  pt: 'pt-PT', it: 'it-IT', ru: 'ru-RU', nl: 'nl-NL', tr: 'tr-TR', pl: 'pl-PL', ja: 'ja-JP',
  ko: 'ko-KR', zh: 'zh-CN', vi: 'vi-VN', id: 'id-ID', th: 'th-TH', he: 'he-IL', fa: 'fa-IR',
};

const KB_ORDER = ['connect', 'media', 'schedule', 'trouble', 'generate', 'identity'];

function matchKb(text, lang) {
  const content = LANG_CONTENT[lang] || LANG_CONTENT.en;
  const lower = text.toLowerCase();
  let best = null;
  let bestScore = 0;
  for (const id of KB_ORDER) {
    const entry = content.kb[id];
    if (!entry) continue;
    let score = 0;
    for (const kw of entry.keywords) {
      if (lower.includes(kw.toLowerCase())) score += 1;
    }
    if (score > bestScore) {
      bestScore = score;
      best = id;
    }
  }
  return best;
}

function GuideBot({ onNavigate }) {
  const { language } = useLanguage();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const bodyRef = useRef(null);
  const timerRef = useRef(null);
  const voiceOnRef = useRef(false);
  const lastBotTextRef = useRef('');

  const content = LANG_CONTENT[language] || LANG_CONTENT.en;
  const voiceLang = VOICE_BY_LANG[language] || language;

  const cancelSpeech = () => {
    try {
      window.speechSynthesis?.cancel();
    } catch {
      /* ignore */
    }
  };

  const deactivateVoice = () => {
    voiceOnRef.current = false;
    setVoiceOn(false);
  };

  const stopSpeech = () => {
    cancelSpeech();
    deactivateVoice();
  };

  const speak = (text) => {
    const payload = (text || '').trim();
    if (!payload) {
      deactivateVoice();
      return false;
    }
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      deactivateVoice();
      return false;
    }
    try {
      // Must be invoked directly from a user gesture (the speaker click).
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(payload);
      utterance.text = payload; // guarantees the bot response is read
      utterance.lang = voiceLang; // selected app language, e.g. 'en-US', 'ur-PK', 'ar-SA'
      utterance.rate = 1;
      const voices = window.speechSynthesis.getVoices();
      const prefix = voiceLang.split('-')[0].toLowerCase();
      const match = voices.find((v) => (v.lang || '').toLowerCase().startsWith(prefix));
      if (match) utterance.voice = match;
      utterance.onstart = () => {
        voiceOnRef.current = true;
        setVoiceOn(true);
      };
      utterance.onend = () => deactivateVoice();
      utterance.onerror = () => deactivateVoice();
      window.speechSynthesis.speak(utterance);
      // Optimistic — flip the icon immediately on the user click.
      voiceOnRef.current = true;
      setVoiceOn(true);
      return true;
    } catch (err) {
      console.error('[GuideBot] speechSynthesis failed:', err);
      deactivateVoice();
      return false;
    }
  };

  const addBotMessages = (lines) => {
    setTyping(true);
    cancelSpeech();
    const joined = lines.join('. ');
    lastBotTextRef.current = joined;
    timerRef.current = setTimeout(() => {
      setMessages((prev) => [...prev, { role: 'bot', lines }]);
      setTyping(false);
      if (voiceOnRef.current) speak(joined); // voice reads the actual bot response
    }, 420);
  };

  const replyTo = (text) => {
    const hit = matchKb(text, language);
    if (hit === 'identity') {
      addBotMessages([content.developedBy]);
    } else if (hit && content.kb[hit]) {
      addBotMessages(content.kb[hit].lines);
      if (hit === 'schedule' && onNavigate) {
        timerRef.current = setTimeout(() => onNavigate('/scheduler'), 260);
      }
    } else {
      addBotMessages([content.fallback]);
    }
  };

  const send = (text) => {
    const clean = (text || '').trim();
    if (!clean || typing) return;
    setMessages((prev) => [...prev, { role: 'user', text: clean }]);
    setInput('');
    replyTo(clean);
  };

  const toggleVoice = () => {
    if (voiceOnRef.current) {
      stopSpeech();
      return;
    }
    // Speak the last bot response if there is one, otherwise the welcome line.
    const text = lastBotTextRef.current ? lastBotTextRef.current : content.welcome;
    deactivateVoice(); // clear any dead state before re-arming
    speak(text);
  };

  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return undefined;
    const warm = () => window.speechSynthesis.getVoices();
    warm();
    if (typeof window.speechSynthesis.addEventListener === 'function') {
      window.speechSynthesis.addEventListener('voiceschanged', warm);
    }
    return () => {
      clearTimeout(timerRef.current);
      if (typeof window.speechSynthesis.removeEventListener === 'function') {
        window.speechSynthesis.removeEventListener('voiceschanged', warm);
      }
      cancelSpeech();
    };
  }, []);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, typing, open, language]);

  // Re-speak nothing on language change; just re-render labels in the new language.
  return (
    <>
      {open && (
        <div className="guidebot-window">
          <div className="guidebot-header">
            <div className="guidebot-avatar">🤖</div>
            <div>
              <div className="guidebot-title">BrandAura Guide</div>
              <div className="guidebot-status">● Online — expert help</div>
            </div>
            <button
              className={`guidebot-voice ${voiceOn ? 'active' : ''}`}
              onClick={toggleVoice}
              title={voiceOn ? 'Voice: on' : 'Voice: off'}
              aria-label="Toggle voice"
            >
              {voiceOn ? '🔊' : '🔇'}
            </button>
            <button className="guidebot-close" onClick={() => setOpen(false)} aria-label="Close guide">✕</button>
          </div>

          <div className="guidebot-body" ref={bodyRef}>
            <div className="guidebot-msg bot">
              <div className="guidebot-bubble">
                <p>{content.welcome}</p>
              </div>
            </div>
            {messages.map((m, i) => (
              <div key={i} className={`guidebot-msg ${m.role}`}>
                <div className={`guidebot-bubble ${m.role === 'bot' ? '' : 'user'}`}>
                  {m.role === 'bot' && m.lines
                    ? m.lines.map((l, j) => <p key={j}>{l}</p>)
                    : <p>{m.text}</p>}
                </div>
              </div>
            ))}
            {typing && <div className="guidebot-msg bot"><div className="guidebot-bubble"><span className="guidebot-typing">● ● ●</span></div></div>}
          </div>

          <div className="guidebot-quick">
            <button className="guidebot-chip" onClick={() => send(content.quick.connect)}>{content.quick.connect}</button>
            <button className="guidebot-chip" onClick={() => send(content.quick.media)}>{content.quick.media}</button>
            <button className="guidebot-chip" onClick={() => send(content.quick.schedule)}>{content.quick.schedule}</button>
            <button className="guidebot-chip" onClick={() => send(content.quick.trouble)}>{content.quick.trouble}</button>
          </div>

          <div className="guidebot-input-row">
            <input
              className="guidebot-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send(input); }}
              placeholder="Ask about BrandAura…"
            />
            <button className="guidebot-send" onClick={() => send(input)} disabled={typing || !input.trim()}>➤</button>
          </div>
        </div>
      )}

      <button
        className="guidebot-fab"
        onClick={() => setOpen((o) => !o)}
        aria-label="Toggle BrandAura guide"
        title="BrandAura guide"
      >
        {open ? '✕' : '🤖'}
      </button>
    </>
  );
}

export default GuideBot;