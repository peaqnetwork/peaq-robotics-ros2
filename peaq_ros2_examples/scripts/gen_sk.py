#!/usr/bin/env python3
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

if __name__ == '__main__':
    print(SigningKey.generate().encode(encoder=HexEncoder).decode())


