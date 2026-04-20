import Foundation

public struct I18NFactory {
    public let locales: LocaleSource
    public init() { self.locales = AssetLocaleSource() }
}
