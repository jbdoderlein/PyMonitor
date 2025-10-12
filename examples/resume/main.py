import spacetimepy

GAME_N = 0

@spacetimepy.pymonitor()
def play_game():
    global GAME_N
    GAME_N += 1
    print(f"Playing game {GAME_N}")

if __name__ == "__main__":
    spacetimepy.init_monitoring(db_path="main.db")
    spacetimepy.start_session("Main")
    for i in range(10):
        play_game()
    spacetimepy.end_session()
