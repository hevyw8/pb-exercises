from binascii import hexlify, unhexlify
from subprocess import check_output
from unittest import TestCase, TestSuite, TextTestRunner

import hashlib
import json


SIGHASH_ALL = 1
SIGHASH_NONE = 2
SIGHASH_SINGLE = 3
BASE58_ALPHABET = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def run_test(test):
    suite = TestSuite()
    suite.addTest(test)
    TextTestRunner().run(suite)


def bytes_to_str(b, encoding='ascii'):
    '''Returns a string version of the bytes'''
    return b.decode(encoding)


def str_to_bytes(s, encoding='ascii'):
    '''Returns a bytes version of the string'''
    return s.encode(encoding)


def hash160(s):
    return hashlib.new('ripemd160', hashlib.sha256(s).digest()).digest()


def double_sha256(s):
    return hashlib.sha256(hashlib.sha256(s).digest()).digest()


def encode_base58(s):
    # determine how many 0 bytes (b'\x00') s starts with
    count = 0
    for c in s:
        if c == 0:
            count += 1
        else:
            break
    prefix = b'1' * count
    # convert from binary to hex, then hex to integer
    num = int(hexlify(s), 16)
    result = bytearray()
    while num > 0:
        num, mod = divmod(num, 58)
        result.insert(0, BASE58_ALPHABET[mod])

    return prefix + bytes(result)


def encode_base58_checksum(s):
    return encode_base58(s + double_sha256(s)[:4]).decode('ascii')


def decode_base58(s):
    num = 0
    for c in s.encode('ascii'):
        num *= 58
        num += BASE58_ALPHABET.index(c)
    # disregard the prefix and checksum
    return num.to_bytes(25, byteorder='big')[1:-4]


def read_varint(s):
    '''read_varint reads a variable integer from a stream'''
    i = s.read(1)[0]
    if i == 0xfd:
        # 0xfd means the next two bytes are the number
        return little_endian_to_int(s.read(2))
    elif i == 0xfe:
        # 0xfe means the next four bytes are the number
        return little_endian_to_int(s.read(4))
    elif i == 0xff:
        # 0xff means the next eight bytes are the number
        return little_endian_to_int(s.read(8))
    else:
        # anything else is just the integer
        return i


def encode_varint(i):
    '''encodes an integer as a varint'''
    if i < 0xfd:
        return bytes([i])
    elif i < 0x10000:
        return b'\xfd' + int_to_little_endian(i, 2)
    elif i < 0x100000000:
        return b'\xfe' + int_to_little_endian(i, 4)
    elif i < 0x10000000000000000:
        return b'\xff' + int_to_little_endian(i, 8)
    else:
        raise RuntimeError('integer too large: {}'.format(i))


def fetch_tx(tx_hash, testnet=False):
    '''Returns the transaction json from a libbitcoin server'''
    command = ['bx', 'fetch-tx', '-f', 'json', '-c']
    if testnet:
        command.append('bx-testnet.cfg')
    else:
        command.append('bx.cfg')
    command.append(hexlify(tx_hash).decode('ascii'))
    return json.loads(check_output(command).decode('ascii'))


def fetch_script_pubkey(tx_hash, tx_index, testnet=False):
    '''Returns the scriptPubKey from the libbitcoin server'''
    tx_data = fetch_tx(tx_hash, testnet)
    output = tx_data['transaction']['outputs'][tx_index]
    script = output['script']
    h160 = output['address_hash']
    # hacky: interpret the script as p2pkh or p2sh
    if script.startswith('dup hash160 [') and script.endswith('] equalverify checksig'):
        return unhexlify('76a914' + h160 + '88ac')
    elif script.startswith('hash160 [') and script.endswith('] equal'):
        return unhexlify('a914' + h160 + '87')
    else:
        raise RuntimeError('unknown script: {}'.format(script))


def flip_endian(h):
    '''flip_endian takes a hex string and flips the endianness
    Returns a hexadecimal string
    '''
    # convert hex to binary (use unhexlify)
    b = unhexlify(h)
    # reverse the binary (use [::-1])
    b_rev = b[::-1]
    # convert binary to hex (use hexlify and then .decode('ascii'))
    return hexlify(b_rev).decode('ascii')


def little_endian_to_int(b):
    '''little_endian_to_int takes byte sequence as a little-endian number.
    Returns an integer'''
    # use the from_bytes method of int
    return int.from_bytes(b, 'little')


def int_to_little_endian(n, length):
    '''endian_to_little_endian takes an integer and returns the little-endian
    byte sequence of length'''
    # use the to_bytes method of n
    return n.to_bytes(length, 'little')


class HelperTest(TestCase):

    def test_bytes(self):

        b = b'hello world'
        s = 'hello world'
        self.assertEqual(b, str_to_bytes(s))
        self.assertEqual(s, bytes_to_str(b))

    def test_base58(self):
        addr = 'mnrVtF8DWjMu839VW3rBfgYaAfKk8983Xf'
        h160 = hexlify(decode_base58(addr))
        want = b'507b27411ccf7f16f10297de6cef3f291623eddf'
        self.assertEqual(h160, want)
        got = encode_base58_checksum(b'\x6f' + unhexlify(h160))
        self.assertEqual(got, addr)

    def test_flip_endian(self):
        h = '03ee4f7a4e68f802303bc659f8f817964b4b74fe046facc3ae1be4679d622c45'
        w = '452c629d67e41baec3ac6f04fe744b4b9617f8f859c63b3002f8684e7a4fee03'
        self.assertEqual(flip_endian(h), w)
        h = '813f79011acb80925dfe69b3def355fe914bd1d96a3f5f71bf8303c6a989c7d1'
        w = 'd1c789a9c60383bf715f3f6ad9d14b91fe55f3deb369fe5d9280cb1a01793f81'
        self.assertEqual(flip_endian(h), w)

    def test_little_endian_to_int(self):
        h = unhexlify('99c3980000000000')
        want = 10011545
        self.assertEqual(little_endian_to_int(h), want)
        h = unhexlify('a135ef0100000000')
        want = 32454049
        self.assertEqual(little_endian_to_int(h), want)

    def test_int_to_little_endian(self):
        n = 1
        want = b'\x01\x00\x00\x00'
        self.assertEqual(int_to_little_endian(n, 4), want)
        n = 10011545
        want = b'\x99\xc3\x98\x00\x00\x00\x00\x00'
        self.assertEqual(int_to_little_endian(n, 8), want)
