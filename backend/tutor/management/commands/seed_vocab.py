"""Seed the three practice topics with vocabulary, and create the demo learner.

Idempotent: re-running updates existing rows rather than duplicating them, so
it is safe to run after every deploy.

    python manage.py seed_vocab
    python manage.py seed_vocab --reset   # wipe vocab and scheduling state first
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from tutor.models import (
    DAILY_ROUTINE,
    ORDERING_FOOD,
    TRAVEL_BASICS,
    ConversationSession,
    UserVocabState,
    VocabItem,
)

# (spanish, english, part_of_speech, example_es, example_en, difficulty)
VOCAB = {
    DAILY_ROUTINE: [
        ('despertarse', 'to wake up', 'verb',
         'Me despierto a las siete.', 'I wake up at seven.', 1),
        ('levantarse', 'to get up', 'verb',
         'Me levanto temprano.', 'I get up early.', 1),
        ('desayunar', 'to have breakfast', 'verb',
         'Desayuno pan y café.', 'I have bread and coffee for breakfast.', 1),
        ('ducharse', 'to shower', 'verb',
         'Me ducho por la mañana.', 'I shower in the morning.', 1),
        ('vestirse', 'to get dressed', 'verb',
         'Me visto rápido.', 'I get dressed quickly.', 2),
        ('cepillarse los dientes', "to brush one's teeth", 'phrase',
         'Me cepillo los dientes.', 'I brush my teeth.', 2),
        ('el trabajo', 'work, job', 'noun',
         'Voy al trabajo en autobús.', 'I go to work by bus.', 1),
        ('almorzar', 'to have lunch', 'verb',
         'Almuerzo a la una.', 'I have lunch at one.', 1),
        ('cenar', 'to have dinner', 'verb',
         'Cenamos a las ocho.', 'We have dinner at eight.', 1),
        ('acostarse', 'to go to bed', 'verb',
         'Me acuesto a las once.', 'I go to bed at eleven.', 2),
        ('la mañana', 'morning', 'noun',
         'Por la mañana leo.', 'In the morning I read.', 1),
        ('la tarde', 'afternoon', 'noun',
         'Estudio por la tarde.', 'I study in the afternoon.', 1),
        ('la noche', 'night', 'noun',
         'Trabajo por la noche.', 'I work at night.', 1),
        ('temprano', 'early', 'adverb',
         'Me levanto muy temprano.', 'I get up very early.', 1),
        ('tarde', 'late', 'adverb',
         'Llego tarde al trabajo.', 'I arrive late to work.', 2),
        ('siempre', 'always', 'adverb',
         'Siempre desayuno en casa.', 'I always have breakfast at home.', 1),
        ('a veces', 'sometimes', 'phrase',
         'A veces corro por la mañana.', 'Sometimes I run in the morning.', 2),
        ('antes de', 'before', 'preposition',
         'Antes de dormir leo un libro.', 'Before sleeping I read a book.', 2),
        ('después de', 'after', 'preposition',
         'Después de cenar veo la tele.', 'After dinner I watch TV.', 2),
        ('descansar', 'to rest', 'verb',
         'Descanso el domingo.', 'I rest on Sunday.', 1),
    ],
    ORDERING_FOOD: [
        ('la mesa', 'table', 'noun',
         'Una mesa para dos, por favor.', 'A table for two, please.', 1),
        ('el menú', 'menu', 'noun',
         '¿Me trae el menú?', 'Could you bring me the menu?', 1),
        ('el camarero', 'waiter', 'noun',
         'El camarero es muy amable.', 'The waiter is very kind.', 1),
        ('pedir', 'to order', 'verb',
         'Quiero pedir la paella.', 'I want to order the paella.', 2),
        ('la cuenta', 'the bill, the check', 'noun',
         'La cuenta, por favor.', 'The bill, please.', 1),
        ('el agua', 'water', 'noun',
         'Un vaso de agua, por favor.', 'A glass of water, please.', 1),
        ('el vino', 'wine', 'noun',
         'Una copa de vino tinto.', 'A glass of red wine.', 1),
        ('el pan', 'bread', 'noun',
         '¿Nos trae más pan?', 'Could you bring us more bread?', 1),
        ('el plato', 'dish, plate', 'noun',
         'Este plato está delicioso.', 'This dish is delicious.', 1),
        ('la bebida', 'drink', 'noun',
         '¿Qué bebida quiere?', 'What would you like to drink?', 1),
        ('el postre', 'dessert', 'noun',
         'De postre, un flan.', 'For dessert, a flan.', 2),
        ('la ensalada', 'salad', 'noun',
         'Una ensalada mixta, por favor.', 'A mixed salad, please.', 1),
        ('el pollo', 'chicken', 'noun',
         'Pollo con arroz.', 'Chicken with rice.', 1),
        ('la carne', 'meat', 'noun',
         'No como carne.', "I don't eat meat.", 1),
        ('el pescado', 'fish', 'noun',
         'El pescado está muy fresco.', 'The fish is very fresh.', 1),
        ('picante', 'spicy', 'adjective',
         '¿Es muy picante?', 'Is it very spicy?', 2),
        ('para llevar', 'to take away', 'phrase',
         'Es para llevar.', "It's to take away.", 2),
        ('quisiera', 'I would like', 'phrase',
         'Quisiera un café, por favor.', 'I would like a coffee, please.', 2),
        ('¿cuánto cuesta?', 'how much does it cost?', 'phrase',
         '¿Cuánto cuesta el menú del día?', 'How much is the set menu?', 2),
        ('soy alérgico a', "I'm allergic to", 'phrase',
         'Soy alérgico a los frutos secos.', "I'm allergic to nuts.", 3),
    ],
    TRAVEL_BASICS: [
        ('el aeropuerto', 'airport', 'noun',
         'Voy al aeropuerto en taxi.', "I'm going to the airport by taxi.", 1),
        ('el billete', 'ticket', 'noun',
         'Un billete a Madrid, por favor.', 'A ticket to Madrid, please.', 1),
        ('la estación', 'station', 'noun',
         'La estación está cerca.', 'The station is close by.', 1),
        ('el tren', 'train', 'noun',
         'El tren sale a las nueve.', 'The train leaves at nine.', 1),
        ('el autobús', 'bus', 'noun',
         'Tomo el autobús al centro.', 'I take the bus downtown.', 1),
        ('el hotel', 'hotel', 'noun',
         'El hotel está en el centro.', 'The hotel is downtown.', 1),
        ('la habitación', 'room', 'noun',
         'Una habitación doble, por favor.', 'A double room, please.', 2),
        ('la maleta', 'suitcase', 'noun',
         'Mi maleta es azul.', 'My suitcase is blue.', 1),
        ('el pasaporte', 'passport', 'noun',
         'Aquí está mi pasaporte.', 'Here is my passport.', 1),
        ('¿dónde está?', 'where is?', 'phrase',
         '¿Dónde está el baño?', 'Where is the bathroom?', 1),
        ('a la derecha', 'to the right', 'phrase',
         'Gire a la derecha.', 'Turn right.', 2),
        ('a la izquierda', 'to the left', 'phrase',
         'El museo está a la izquierda.', 'The museum is on the left.', 2),
        ('cerca', 'near', 'adverb',
         'La playa está cerca.', 'The beach is near.', 1),
        ('lejos', 'far', 'adverb',
         'El aeropuerto está lejos.', 'The airport is far.', 1),
        ('perdido', 'lost', 'adjective',
         'Estoy perdido.', "I'm lost.", 2),
        ('el mapa', 'map', 'noun',
         '¿Tiene un mapa de la ciudad?', 'Do you have a map of the city?', 1),
        ('reservar', 'to book, to reserve', 'verb',
         'Quiero reservar una habitación.', 'I want to book a room.', 2),
        ('el vuelo', 'flight', 'noun',
         'Mi vuelo se retrasó.', 'My flight was delayed.', 2),
        ('¿a qué hora sale?', 'what time does it leave?', 'phrase',
         '¿A qué hora sale el tren?', 'What time does the train leave?', 2),
        ('la ayuda', 'help', 'noun',
         'Necesito ayuda, por favor.', 'I need help, please.', 1),
    ],
}


class Command(BaseCommand):
    help = 'Seed the three topics with vocabulary and create the demo learner.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing vocab, scheduling state and sessions first.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            session_count = ConversationSession.objects.count()
            state_count = UserVocabState.objects.count()
            vocab_count = VocabItem.objects.count()
            ConversationSession.objects.all().delete()
            UserVocabState.objects.all().delete()
            VocabItem.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                f'--reset: removed {vocab_count} vocab items, '
                f'{state_count} scheduling states, {session_count} sessions.'
            ))

        created_total = updated_total = 0
        for topic, entries in VOCAB.items():
            created = updated = 0
            for spanish, english, pos, example_es, example_en, difficulty in entries:
                _item, was_created = VocabItem.objects.update_or_create(
                    topic=topic,
                    spanish=spanish,
                    defaults={
                        'english': english,
                        'part_of_speech': pos,
                        'example_es': example_es,
                        'example_en': example_en,
                        'difficulty': difficulty,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            created_total += created
            updated_total += updated
            label = dict(VocabItem._meta.get_field('topic').choices)[topic]
            self.stdout.write(
                f'  {label:<16} {created:>2} created, {updated:>2} updated '
                f'({len(entries)} total)'
            )

        demo_user, user_created = User.objects.get_or_create(
            username=settings.DEMO_USERNAME,
            defaults={'first_name': 'Demo', 'last_name': 'Learner'},
        )
        if user_created:
            # The demo learner is never logged into, so give it no usable
            # password rather than inventing a credential.
            demo_user.set_unusable_password()
            demo_user.save(update_fields=['password'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {VocabItem.objects.count()} vocab items across '
            f'{len(VOCAB)} topics '
            f'({created_total} created, {updated_total} updated).'
        ))
        self.stdout.write(
            f'Demo learner "{demo_user.username}": '
            f'{"created" if user_created else "already existed"}.'
        )
