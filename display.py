from machine import Pin, SPI
import gc9a01py as gc9a01
from config import (
    PIN_DISP_CS, PIN_DISP_MOSI, PIN_DISP_SCK,
    PIN_DISP_DC, PIN_DISP_RST,
    DISP_WIDTH, DISP_HEIGHT, DISP_SPI_FREQ,
)


def init() -> gc9a01.GC9A01:
    """Initialise and return the display object."""
    spi = SPI(
        1,
        baudrate=DISP_SPI_FREQ,
        polarity=0,
        phase=0,
        sck=Pin(PIN_DISP_SCK),
        mosi=Pin(PIN_DISP_MOSI),
    )
    display = gc9a01.GC9A01(
        spi,
        dc=Pin(PIN_DISP_DC,  Pin.OUT),
        cs=Pin(PIN_DISP_CS,  Pin.OUT),
        reset=Pin(PIN_DISP_RST, Pin.OUT),
        rotation=0,
    )
    display.fill(gc9a01.BLACK)
    return display
