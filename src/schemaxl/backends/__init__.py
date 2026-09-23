"""出力バックエンド層。

PlacementPlan を物理ファイルへ書き出す副作用の境界。
共通インターフェースは `base.Backend`。MVP の実装は openpyxl バックエンドのみ。
将来は LibreOffice / PDF 等を追加予定。
"""
