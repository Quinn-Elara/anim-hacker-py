import sys


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        sys.stderr.write("Anim Hacker needs PySide6. Install it with:  pip install PySide6\n")
        return 1
    from .ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName("Anim Hacker")
    window = MainWindow()
    window.show()
    if len(argv) > 1:
        window.load_path(argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
