import monitoringpy

GAME_N = 0

@monitoringpy.pymonitor()
def play_game():
    global GAME_N
    GAME_N += 2
    print(f"Playing game {GAME_N}")

if __name__ == "__main__":
    monitoringpy.init_monitoring(db_path="main.db")
    monitoringpy.start_session("Main")
    for i in range(10):
        play_game()
    monitoringpy.end_session()
