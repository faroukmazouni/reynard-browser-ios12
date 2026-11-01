//
//  Data+SHA256.swift
//  Reynard
//
//  SHA-256 hex digest. Uses CryptoKit on iOS 13+, CommonCrypto on iOS 12
//  (CryptoKit is iOS 13+). See IOS12_GATES.md.
//

import Foundation
import CommonCrypto

extension Data {
    var sha256Hex: String {
        var digest = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        withUnsafeBytes { buffer in
            _ = CC_SHA256(buffer.baseAddress, CC_LONG(count), &digest)
        }
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}
