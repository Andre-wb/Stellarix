import Foundation

public struct I18NFactory {
    public let locales: LocaleSource
    @MainActor public let localizer: Localizer

    @MainActor public init() {
        self.locales = AssetLocaleSource()
        self.localizer = Localizer()
    }
}
