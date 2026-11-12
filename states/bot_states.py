from aiogram.fsm.state import State, StatesGroup

class AddWordStates(StatesGroup):
    waiting_for_photo = State()       # Waiting specifically for photo/image
    waiting_for_text = State()        # Waiting specifically for typed words/text
    waiting_for_unit_choice = State() # User chooses existing unit or creates new
    waiting_for_new_unit_name = State() # User enters new unit title

class QuizStates(StatesGroup):
    in_progress = State()

class TypingStates(StatesGroup):
    in_progress = State()

class ListeningStates(StatesGroup):
    in_progress = State()

