import random
from abc import ABC, abstractmethod

class IBot(ABC):
    @abstractmethod
    def get_choice(self) -> str:
        """Returns 'C' or 'D'"""
        pass

    @abstractmethod
    def record_result(self, my_last_choice: str, opponent_last_choice: str):
        pass

class CBot(IBot):
    def get_choice(self): return 'C'
    def record_result(self, my_last_choice, opponent_last_choice): pass

class DBot(IBot):
    def get_choice(self): return 'D'
    def record_result(self, my_last_choice, opponent_last_choice): pass

class RandomBot(IBot):
    def get_choice(self):
        return 'C' if random.random() < 0.5 else 'D'
    def record_result(self, my_last_choice, opponent_last_choice): pass

class TitForTatBot(IBot):
    def __init__(self):
        self.is_first_turn = True
        self.opponent_last_move = 'C'

    def get_choice(self):
        if self.is_first_turn:
            return 'C'
        return self.opponent_last_move

    def record_result(self, my_last_choice, opponent_last_choice):
        self.is_first_turn = False
        self.opponent_last_move = opponent_last_choice

class CopycatBot(IBot):
    def __init__(self):
        self.is_first_turn = True
        self.opponent_last_move = 'C'

    def get_choice(self):
        if self.is_first_turn:
            return 'C' if random.random() < 0.5 else 'D'
        return self.opponent_last_move

    def record_result(self, my_last_choice, opponent_last_choice):
        self.is_first_turn = False
        self.opponent_last_move = opponent_last_choice

class MirrorBot(IBot):
    def __init__(self, cooperate_rounds=3, mirror_pct=0.83):
        self.cooperate_rounds = cooperate_rounds
        self.mirror_pct = mirror_pct
        self.round_count = 1
        self.opponent_choice = 'C'
        self.cc_streak = 0

    def set_opponent_choice(self, choice):
        self.opponent_choice = choice

    def get_choice(self):
        if self.round_count <= self.cooperate_rounds:
            return 'C'
        
        if random.random() < self.mirror_pct:
            return self.opponent_choice
        else:
            return 'C' if random.random() < 0.5 else 'D'

    def record_result(self, my_last_choice, opponent_last_choice):
        self.round_count += 1
        if my_last_choice == 'C' and opponent_last_choice == 'C':
            self.cc_streak += 1
        else:
            self.cc_streak = 0

class SERSBot(IBot):
    def __init__(self, stack_size, is_player_1, p1_A_meaning, p2_A_meaning, 
                 aa1, ab1, ba1, bb1, aa2, ab2, ba2, bb2):
        self.SERS_STACK = stack_size
        self.session_history = []
        self.is_player_1 = is_player_1
        self.p1_A_meaning = p1_A_meaning
        self.p2_A_meaning = p2_A_meaning
        self.AA1, self.AB1, self.BA1, self.BB1 = aa1, ab1, ba1, bb1
        self.AA2, self.AB2, self.BA2, self.BB2 = aa2, ab2, ba2, bb2
        self.next_choice = 'C'
        self.calculate_next_choice()

    def calculate_ps(self):
        if not self.session_history: return 0.5
        games_to_consider = min(self.SERS_STACK, len(self.session_history))
        similar_choices = sum(1 for h in self.session_history[-games_to_consider:] if h['p1'] == h['p2'])
        return similar_choices / games_to_consider

    def calculate_next_choice(self):
        ps = self.calculate_ps()
        EV_A = 0.0
        EV_B = 0.0
        same_meaning = (self.p1_A_meaning == self.p2_A_meaning)

        if self.is_player_1:
            if same_meaning:
                EV_A = ps * self.AA1 + (1.0 - ps) * self.AB1
                EV_B = ps * self.BB1 + (1.0 - ps) * self.BA1
            else:
                EV_A = ps * self.AB1 + (1.0 - ps) * self.AA1
                EV_B = ps * self.BA1 + (1.0 - ps) * self.BB1
        else:
            if same_meaning:
                EV_A = ps * self.AA2 + (1.0 - ps) * self.BA2
                EV_B = ps * self.BB2 + (1.0 - ps) * self.AB2
            else:
                EV_A = ps * self.BA2 + (1.0 - ps) * self.AA2
                EV_B = ps * self.AB2 + (1.0 - ps) * self.BB2

        if EV_A > EV_B:
            best_button = 'A'
        elif EV_A < EV_B:
            best_button = 'B'
        else:
            best_button = 'A' if random.random() < 0.5 else 'B'
            
        p_a_mean = self.p1_A_meaning if self.is_player_1 else self.p2_A_meaning
        if best_button == 'A':
            self.next_choice = 'C' if str(p_a_mean).lower().startswith('c') else 'D'
        else:
            self.next_choice = 'D' if str(p_a_mean).lower().startswith('c') else 'C'

    def get_choice(self):
        return self.next_choice

    def record_result(self, my_last_choice, opponent_last_choice):
        if self.is_player_1:
            my_meaning = self.p1_A_meaning if my_last_choice == 'C' else "defect"
            op_meaning = self.p2_A_meaning if opponent_last_choice == 'C' else "defect"
            self.session_history.append({'p1': my_meaning, 'p2': op_meaning})
        else:
            my_meaning = self.p2_A_meaning if my_last_choice == 'C' else "defect"
            op_meaning = self.p1_A_meaning if opponent_last_choice == 'C' else "defect"
            self.session_history.append({'p1': op_meaning, 'p2': my_meaning})
            
        self.calculate_next_choice()

def create_bot(bot_type, is_player_1, session_data):
    if bot_type == 'CBot': return CBot()
    if bot_type == 'DBot': return DBot()
    if bot_type == 'Random': return RandomBot()
    if bot_type == 'TitForTat': return TitForTatBot()
    if bot_type == 'Copycat': return CopycatBot()
    if bot_type == 'MirrorBot':
        return MirrorBot(
            cooperate_rounds=session_data.get('cooperate_rounds', 3),
            mirror_pct=session_data.get('mirror_pct', 0.83)
        )
    
    if bot_type.startswith('SERS_'):
        stack_size = int(bot_type.split('_')[1])
        p1_a_mean = str(session_data.get('P1_A_MEANING', 'C'))
        p2_a_mean = str(session_data.get('P2_A_MEANING', 'C'))
        return SERSBot(stack_size, is_player_1, p1_a_mean, p2_a_mean, 
                       session_data['AA1'], session_data['AB1'], session_data['BA1'], session_data['BB1'],
                       session_data['AA2'], session_data['AB2'], session_data['BA2'], session_data['BB2'])
    return RandomBot()
