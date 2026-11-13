-- VetCare: URL pública de PDF asociado a cada carné digital.
-- Ejecución segura en esquemas donde la migración aún no se aplicó.
DECLARE
    PROCEDURE add_column_if_missing(p_name VARCHAR2, p_definition VARCHAR2) IS
        v_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_count
        FROM user_tab_columns
        WHERE table_name = 'PET_DIGITAL_CARDS' AND column_name = UPPER(p_name);
        IF v_count = 0 THEN
            EXECUTE IMMEDIATE 'ALTER TABLE PET_DIGITAL_CARDS ADD (' || p_name || ' ' || p_definition || ')';
        END IF;
    END;
BEGIN
    add_column_if_missing('PUBLIC_PDF_URL', 'VARCHAR2(1000)');
    add_column_if_missing('PDF_PUBLISHED_AT', 'TIMESTAMP WITH TIME ZONE');
    add_column_if_missing('PDF_UPLOAD_STATUS', 'VARCHAR2(20) DEFAULT ''NOT_PUBLISHED'' NOT NULL');
END;
/
