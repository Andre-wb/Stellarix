// Точка входа для десктопной версии
// Для Android используется mobile_main из lib.rs

#[cfg(not(target_os = "android"))]
fn main() {
    stellarix_desktop_lib::run_desktop();
}