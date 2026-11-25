-- Ejecutar como VETCARE; aditiva e idempotente. No cambia productos ni ventas.
-- BARCODE ya tiene una restricción UNIQUE en el esquema actual.
DECLARE
    v_count PLS_INTEGER;
    PROCEDURE add_column_if_missing(p_name VARCHAR2, p_definition VARCHAR2) IS
        v_columns PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_columns FROM user_tab_columns
        WHERE table_name = 'SALES' AND column_name = UPPER(p_name);
        IF v_columns = 0 THEN
            EXECUTE IMMEDIATE 'ALTER TABLE SALES ADD (' || p_name || ' ' || p_definition || ')';
        END IF;
    END;
BEGIN
    add_column_if_missing('REQUEST_KEY', 'VARCHAR2(32)');
    add_column_if_missing('REQUEST_HASH', 'VARCHAR2(64)');
    SELECT COUNT(*) INTO v_count FROM user_constraints
    WHERE table_name = 'SALES' AND constraint_name = 'UQ_SALES_REQUEST_KEY';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE SALES ADD CONSTRAINT UQ_SALES_REQUEST_KEY UNIQUE (REQUEST_KEY)';
    END IF;
END;
/
