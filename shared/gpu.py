# (c) Copyright 2023 by Coinkite Inc. This file is covered by license found in COPYING-CC.
#
# gpu.py - GPU co-processor access and support.
#
# - see notes in misc/gpu/README.md
# - bl = Bootloader, provided by ST Micro in ROM of chip
# - useful: import gpu; g=gpu.GPUAccess(); g.enter_bl()
#
import utime, struct
import uasyncio as asyncio
from utils import B2A
from machine import Pin

# boot loader ROM response to this I2C address
BL_ADDR = const(0x64)
# my GPU micro code responses to this I2C address
GPU_ADDR = const(0x65)

BL_ACK = b'y'       # 0x79
BL_NACK = b'\x1f'
BL_BUSY = b'v'      # 0x76

FLASH_START = const(0x0800_0000)

def add_xor_check(lst):
    # byte-wise xor over list of bytes (used as a very weak checksum in BL)
    rv = 0x0
    for b in lst:
        rv ^= b
    return bytes(lst + bytes([rv]))

class GPUAccess:
    def __init__(self):
        # much sharing/overlap in these pins!
        # - pins are already setup in bootloader, no need to change here
        self.g_reset = Pin('G_RESET')           #, mode=Pin.OPEN_DRAIN, pull=Pin.PULL_UP)
        self.g_boot0 = Pin('G_SWCLK_B0')        #, mode=Pin.IN)
        self.g_ctrl = Pin('G_CTRL')             #, mode=Pin.OUT_PP, value=1)
        self.mosi_pin = Pin('LCD_MOSI')
        self.sclk_pin = Pin('LCD_SCLK')

        from machine import I2C
        self.i2c = I2C(1, freq=400000)      # same bus & speed as nfc.py

        # let the GPU run
        self.g_reset(1)

    def bl_cmd_read(self, cmd, expect_len, addr=None, arg2=None, no_final=False):
        # send a one-byte command to bootloader ROM and get response
        # - need len to expect, because limitations of hard i2c on this setup
        i2c = self.i2c

        self._send_cmd(cmd)

        if addr is not None:
            if isinstance(addr, int):
                # write 4 bytes of address
                qq = add_xor_check(struct.pack('>I', addr))
            else:
                qq = bytes(addr)

            i2c.writeto(BL_ADDR, qq)

            resp = i2c.readfrom(BL_ADDR, 1)
            if resp != BL_ACK:
                raise ValueError('bad addr')

        if arg2 is not None:
            # write second argument, might be a length or date to be written
            if isinstance(arg2, int):
                i2c.writeto(BL_ADDR, bytes([arg2, 0xff ^ arg2]))
            else:
                i2c.writeto(BL_ADDR, add_xor_check(arg2))

            resp = i2c.readfrom(BL_ADDR, 1)
            if resp != BL_ACK:
                raise ValueError('bad arg2')

        if expect_len == 0:
            return

        # for some commands, first byte of response is length and it can vary
        # - however, they are inconsistent on how they count that and not
        #   all commands use it, etc.
        # - tried and failed to check/handle the length here; now caller's problem
        rv = i2c.readfrom(BL_ADDR, expect_len) 

        if not no_final:
            # final ack/nack
            resp = i2c.readfrom(BL_ADDR, 1)
            if resp != BL_ACK:
                raise ValueError(resp)

        return rv

    def _wait_done(self):
        for retry in range(100):
            try:
                resp = self.i2c.readfrom(BL_ADDR, 1)
            except OSError:     # ENODEV
                #print('recover')
                utime.sleep_ms(50)
                continue

            if resp != BL_BUSY:
                break

            #print('busy')
            utime.sleep_ms(20)

        return resp

    def _send_cmd(self, cmd):
        # do just the cmd + ack part
        self.i2c.writeto(BL_ADDR, bytes([cmd, 0xff ^ cmd]))
        resp = self.i2c.readfrom(BL_ADDR, 1)
        if resp != BL_ACK:
            raise ValueError('unknown command')

    def bl_doit(self, cmd, arg):
        # send a one-byte command and an argument, wait until done
        self._send_cmd(cmd)

        self.i2c.writeto(BL_ADDR, add_xor_check(arg))

        return self._wait_done()

    def bl_double_ack(self, cmd):
        # some commands need two acks because they do stuff during that time?
        self._send_cmd(cmd)
        resp = self._wait_done()
        if resp == BL_ACK:
            return self._wait_done()
        return resp

    def reset(self):
        # Pulse reset and let it run
        self.g_boot0.init(mode=Pin.IN)
        self.g_reset(0)
        self.g_reset(1)

    def enter_bl(self):
        # Get it into bootloader. Reliable. Still allows SWD to work.
        self.g_reset(0)
        self.g_boot0.init(mode=Pin.OUT_PP)
        self.g_boot0(1)
        self.g_reset(1)
        self.g_boot0.init(mode=Pin.IN)

    def bl_version(self):
        # assume already in bootloader
        return self.bl_cmd_read(0x0, 20)

    def bulk_erase(self):
        # "No-Stretch Erase Memory" with 0xFFFF arg = "global mass erase"
        return self.bl_doit(0x45, b'\xff\xff') == BL_ACK

    def readout_unprotect(self):
        # "No-Stretch Readout Unprotect" -- may wipe chip in process?
        return self.bl_double_ack(0x93)

    def readout_protect(self):
        # "No-Stretch Readout Protect" 
        return self.bl_double_ack(0x83)

    def read_at(self, addr=FLASH_START+0x100, ln=16):
        # read memory, but address must be "correct" and mapped, which is undocumented
        # - need not be aligned, up to 256
        # - 0x1fff0cd0 also fun: BL code; 0x20001000 => RAM (but wont allow any lower?)
        assert ln <= 256
        return self.bl_cmd_read(0x11, ln, addr=addr, arg2=ln-1, no_final=True)

    def write_at(self, addr=FLASH_START+0x100, data=b'1234'):
        # "No-Stretch Write Memory command"
        # - flash must be erased beforehand, or does nothing (no error)
        ln = len(data)
        assert ln <= 256
        assert ln % 4 == 0
        assert addr % 4 == 0

        arg = add_xor_check(bytes([ln-1]) + data)

        # send cmd, addr
        self.bl_cmd_read(0x32, 0, addr=addr, arg2=None)

        # then second arg, and wait til done
        self.i2c.writeto(BL_ADDR, arg)

        return self._wait_done() == BL_ACK

    def run_at(self, addr=FLASH_START):
        # "Go command" - starts code, but wants a reset vector really (stack+PC values)
        self.bl_cmd_read(0x21, 0, addr=addr)

    def cmd_resp(self, cmd_args, expect_len):
        # send a command and read response back from our code running on GPU
        self.i2c.writeto(GPU_ADDR, cmd_args)
        return self.i2c.readfrom(GPU_ADDR, expect_len)

    def goto_bootloader(self):
        # switch working GPU code into bootloader mode
        resp = self.cmd_resp(b'b', 2)
        assert resp == b'OK'
        self.reset()
        utime.sleep_ms(100)

    def get_version(self):
        # see if running, and what version
        try:
            resp = self.cmd_resp(b'v', 20)
        except OSError:
            try:
                # check bootloader is running
                self.bl_version()
            except:
                return 'FAIL'
            return 'BL'       # ready to load via BL
        return resp[0:resp.index(b'\0')].decode()

    def spi(self, ours=False):
        # change the MOSI/SCLK lines to be input so we don't interfere
        # with the GPU.. other lines are OD
        # - signal by G_CTRL that GPU can take over
        if ours:
            self.g_ctrl(1)
            self.mosi_pin.init(mode=Pin.ALT, pull=Pin.PULL_DOWN, af=Pin.AF5_SPI1)
            self.sclk_pin.init(mode=Pin.ALT, pull=Pin.PULL_DOWN, af=Pin.AF5_SPI1)
        else:
            self.mosi_pin.init(mode=Pin.IN)
            self.sclk_pin.init(mode=Pin.IN)
            self.g_ctrl(0)

    def upgrade(self):
        # do in-circuit programming of GPU chip
        import gpu_binary

        if self.get_version() != 'BL':
            self.goto_bootloader()
        assert self.get_version() == 'BL'

        ok = self.bulk_erase()
        assert ok, 'bulk erase fail'

        for pos in range(256, gpu_binary.LENGTH, 256):
            self.write_at(FLASH_START+pos, gpu_binary.BINARY[pos:pos+256])

        # last! the first part
        self.write_at(FLASH_START, gpu_binary.BINARY[0:256])

        self.run_at(FLASH_START)
        utime.sleep_ms(50)

        v = self.get_version() 
        assert v== gpu_binary.VERSION

        return v
            

# EOF