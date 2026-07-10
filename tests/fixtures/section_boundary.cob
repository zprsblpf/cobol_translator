       IDENTIFICATION DIVISION.
       PROGRAM-ID. SBOUND.
      *> fixture: parser section boundary audit
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 1000-MAIN PIC X(04) VALUE 'SEC'.
       01 WSAA-DATA PIC X(10).
       01 WSAA-FLAG PIC X(01).
       PROCEDURE DIVISION.
      *> entry code between PROCEDURE DIVISION and first SECTION
           MOVE 'OK' TO WSAA-DATA.
       1000-MAIN SECTION.
           MOVE 'A' TO WSAA-FLAG.
           PERFORM 2000-NEXT.
       2000-NEXT SECTION.
           MOVE 'B' TO WSAA-FLAG.
      *>    mock COPY boundary
      *>    COPY SUPPLIB.
       3000-LAST SECTION.
           MOVE 'C' TO WSAA-FLAG.
           GOBACK.
