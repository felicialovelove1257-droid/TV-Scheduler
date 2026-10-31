"""User-visible workflow. Update this file whenever pipeline behavior changes."""
from pathlib import Path
from datetime import datetime

SECTIONS = [
('1. Đọc thông tin đầu vào',
 'Lấy EP theo ngày; nếu bạn sửa thì dùng EP bạn nhập. Giữ lựa chọn FN và TSER FN lần cuối.\n'
 'Đọc thời lượng, số phần FN và câu Next day will air… để xác định chương trình bắt đầu.\n'
 'Lấy giờ ở dòng End cuối làm giờ bắt đầu ngày kế tiếp; tính độ lệch so với 01:00:00. Không lấy mốc set from air end của hôm trước và không tự cộng/trừ ADD hoặc MINUS.'),
('2. Quét và chọn file',
 'Quét nguồn W và thư mục EP trên D. Ưu tiên file thật có sẵn; phần thiếu mới dùng thời lượng báo trước để tạo temp.\n'
 'Nhận tên viết tắt theo quy tắc và bảng chuyển đổi. ADS chưa nhận diện chắc chắn thì không tự chọn làm ADS bù. Thời lượng dùng để tính lịch lấy từ file thực tế.'),
('3. Chuẩn hóa tên và tạo EP',
 'Đặt tên local theo loại show, segment và phiên bản. Tạo temp cho phần thiếu đã có thời lượng; phần còn thiếu dữ liệu được báo lại.\n'
 'Max/No Max ở nguồn được ưu tiên. Tùy chỉnh Max trong thời lượng báo trước chỉ áp dụng cho temp.\n'
 'BMD OUT chọn UP NXT theo show tiếp theo, bỏ qua NWN. WOW lecture có IN/MAIN/OUT; ngày sau là lecture thì không yêu cầu TSER WOW. TSER FN theo ô tick.\n'
 'FN: P1 chia P1A/P1B; bộ EP lớn hơn phát trước, cùng EP thì bản mới trước reair.'),
('AP Chủ nhật và teaser 3 ngày',
 'AP thay WOW ở cùng vị trí trong cycle. Nhận từ bảng lịch/file của EP; lịch tuần lấy EP 3309 làm mốc AP Chủ nhật, không dựa vào ngày bấm chạy.\n'
 'AP phát PART A → B → C → D → E… liền nhau, số phần theo file/thời lượng đã nhập; thiếu phần ở giữa sẽ báo lỗi; không áp IN/OUT hoặc M intro của WOW và không tự chèn ADS giữa các PART. BMD dẫn tới AP dùng UP NXT AP.\n'
 'TSER AP chạy trước 2 ngày, trước 1 ngày và TODAY: cùng số EP của ngày phát AP. Giữ đúng biến thể IN 2 DAYS / TOMORROW / TODAY nếu tên nguồn có ghi. Không lấy nhầm TODAY cho hôm trước. Teaser WOW ngày sau nếu cần vẫn được giữ riêng.\n'
 'Khi thiếu nguồn, có thể nhập AP PARTA/PARTB/PARTC/PARTD/PARTE… và TSER AP để tạo temp; thiếu thời lượng thì báo lại.'),
('Show dạng IN / MAIN / OUT',
 'Show như AJAR vẫn nằm ở vị trí show bình thường trong vòng xoay. Khi nguồn hoặc thời lượng có IN/INTRO và OUT/OUTRO, PIP chọn IN → MAIN → OUT, không chèn ADS/teaser vào giữa. MAIN có thể chỉ mang mã show và tên chương trình.\n'
 'Thiếu phần nào hoặc có nhiều bản chưa chọn rõ thì báo lại. Max/No Max chọn theo từng phần; OUT No NXT chỉ dùng khi show đó là show cuối phù hợp. Show dạng S1/S2 vẫn theo quy tắc chèn dưới 2 phút.'),
('4. Dựng các cycle',
 'Xoay block theo chương trình bắt đầu. Giữ vị trí ADS giữa các cycle giống nhau theo cấu hình khi có thể.\n'
 'Giữ nội dung chèn giữa các segment. Teaser lặp gần nhau được ưu tiên đổi chỗ với ADS dưới 2 phút trong cùng cycle, nếu giãn được khoảng cách; không đổi ADS đã khóa vị trí. Mỗi chỗ chèn chỉ một mục; ADS từ 2 phút đặt giữa các show. Không thêm lặp một ADS trong cùng cycle.'),
('5. Canh MT — sai số tối đa ±15 giây',
 'Ưu tiên các mốc không ngắt NWN trước S3: thử Max/No Max trước, rồi điều chỉnh ADS trong cycle gần mốc MT.\n'
 'Thử thêm ADS, chuyển ADS xuống sau MT trong cùng cycle nếu còn chỗ, rồi giảm ADS; khi chưa đạt mới mở rộng về cycle trước.\n'
 'Chỉ khi các phương án trên không đạt mới xét đặt MT trước khi NWN phát hết S3. Không cắt ngang nội dung một file.'),
('6. Canh cuối ngày',
 'Giữ trọn show và chọn điểm kết thúc trong khoảng ±15 giây quanh mốc cuối ngày. Khi cần, giảm mục chèn trước khi bỏ show kế tiếp; giữ nội dung chèn bắt buộc giữa segment. Nếu cuối là NWN có thể bỏ Daily Scroll.\n'
 'Chọn No NXT cho show cuối có UP NEXT; NWN không tính. Nếu chưa có bản thật thì dùng temp và ghi trong nhóm thông báo file tạm.\n'
 'Điều chỉnh Max/No Max cuối ngày, rồi thêm tối đa một ADS bù phù hợp thời lượng. Không nhồi nhiều ADS nhỏ và không ưu tiên ADS chỉ vì đang có màu đỏ trong báo cáo sử dụng.\n'
 'ADS bù lấy từ INPUT_4 đã nhận diện chắc chắn. Loại mục có DO NOT AIR, Not Air, Need Fix hoặc báo lỗi trong tên/ghi chú; màu chữ riêng lẻ hiện chưa được đọc.\n'
 'Mục tiêu: cuối ngày được sớm hoặc trễ tối đa 15 giây. Nếu chưa đạt thì lấy phương án phù hợp gần nhất và báo cảnh báo. Mốc tính được điều chỉnh theo độ lệch đầu ngày.'),
('7. Xuất M3U và báo cáo QC',
 'Lưu playlist ở D:\\SMTV_LIVE\\_playlist, tên EP #### v1.m3u. Kiểm tra MT, cuối ngày, thiếu file, vị trí chèn và quy tắc cycle.\n'
 'Nhóm file tạm có thể mở ra xem từng mục. Báo cáo ADS sử dụng: trên 3 cycle màu xanh; 0–3 cycle màu đỏ. Màu đỏ ở báo cáo này không có nghĩa là cấm phát.'),
('Nút riêng: Chuẩn bị file', 'Chuẩn bị file và Update là thao tác riêng, không nằm trong Chạy tất cả. Quét lại file nguồn ngoài Eng và lưu vào EP/temp. Chuẩn bị file chỉ copy mục chưa có trong temp; không thay file đã có.\nUpdate dùng lịch sử trong configs/prepare_history của PIP trên máy đang dùng, tách theo EP và thư mục nguồn: bỏ qua nguồn đã xử lý dù file temp bị xóa; copy nguồn chưa làm hoặc đã đổi dung lượng/thời điểm sửa. Lịch sử được ghi sau mỗi file copy thành công.\nKiểm tra ổn định cả danh sách cần copy trong 5 giây. Bỏ qua file thay đổi/lỗi, báo cáo sau; nút Dừng áp dụng cho cả hai thao tác.'),
]

SECTIONS.insert(3, ('Cập nhật nguồn mới', 'Tất cả chương trình: ưu tiên phiên bản nguồn cao hơn; cùng phiên bản và cùng tên local thì lấy file sửa mới nhất. Khi đường dẫn, dung lượng hoặc thời điểm sửa nguồn thay đổi, Tạo EP cập nhật temp và thời lượng, kể cả tên local đã tồn tại. Bản No Max tự tạo cũng được cập nhật theo nguồn. Kiểm tra nguồn ổn định trước khi cập nhật.'))

SECTIONS.insert(4, ('Số lần teaser mỗi cycle', 'Mỗi teaser được dùng tối đa 1 lần mỗi cycle; riêng TSER FN tối đa 2 lần. Chỗ chèn giữa segment còn thiếu dùng ADS dưới 2 phút; không lặp teaser để lấp chỗ.'))

SECTIONS.insert(1, ('Đọc chuỗi chương trình', 'Thông báo bắt đầu: đọc tiếp chuỗi chương trình sau dấu /, ví dụ BMD followed by NWN FN/WOW là BMD → NWN → WOW, chọn block 7. Vẫn đối chiếu số EP và thứ tự thực tế.'))

SECTIONS.insert(2, ('Hậu tố /WOW và /SHOW', 'Sau NWN: /WOW là đến WOW; /SHOW là đến show đang có trong lịch EP (ví dụ VEG). Đối chiếu vòng block để phân biệt BMD block 7 và block 3; nếu vẫn nhiều khả năng thì yêu cầu chọn tay.'))

SECTIONS.append(('Bộ portable', 'Bộ portable: INPUT.xlsx và @ ADS 2 nằm trong thư mục bộ ứng dụng; kết quả ở _playlist. Có Python, FFmpeg và LibreOffice để sửa bảng không cần Excel. Đường dẫn nguồn W được cấu hình trong portable_settings.json.'))

SECTIONS.append(('ADS đặc biệt', 'ADS đặc biệt bắt buộc: tìm trong @ ADS/zzz SPECIALS và thư mục con, bỏ qua old. Nhận diện tên bỏ chú thích ngày sinh dạng (Oct 9), không đoán tên gần giống. Tạo temp đúng thời lượng trong EP local, giữ tên nguồn và ghi liên kết với tên ADS trong bảng. Khi nguồn đổi thì cập nhật temp.'))

def show_flow(parent):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    window=tk.Toplevel(parent)
    from app_version import APP_VERSION
    window.title('Thứ tự xử lý PIP v'+APP_VERSION)
    window.geometry('820x680')
    window.minsize(580,420)
    header=ttk.Frame(window,padding=14);header.pack(fill='x')
    ttk.Label(header,text='THỨ TỰ XỬ LÝ PIP v'+APP_VERSION,font=('Segoe UI',14,'bold')).pack(anchor='w')
    updated=datetime.fromtimestamp(Path(__file__).stat().st_mtime).strftime('%d/%m/%Y %H:%M')
    ttk.Label(header,text='Quy tắc hiện tại • Cập nhật: '+updated).pack(anchor='w',pady=(5,0))
    ttk.Label(header,text='Đây là hướng dẫn luồng xử lý, không phải tiến độ chạy trực tiếp.').pack(anchor='w',pady=(4,0))
    body=ScrolledText(window,wrap='word',font=('Segoe UI',11),padx=16,pady=12,borderwidth=0)
    body.pack(fill='both',expand=True,padx=12)
    body.tag_configure('heading',font=('Segoe UI',12,'bold'),foreground='#17496d',spacing1=14,spacing3=7)
    body.tag_configure('text',spacing3=10,lmargin1=4,lmargin2=4)
    for title,text in SECTIONS:
        body.insert('end',title+'\n','heading')
        body.insert('end',text+'\n','text')
    body.configure(state='disabled')
    ttk.Button(window,text='Đóng',command=window.destroy).pack(anchor='e',padx=14,pady=12)
    return window

SECTIONS.append(('File temp trên máy lập lịch', 'Tạo EP không copy nguyên video nguồn: đọc thời lượng và tạo temp, kể cả khi đổi tên từ file local có sẵn. Các bước dựng cycle, canh giờ và xuất M3U không copy video. Prepare Files / Update là thao tác riêng trên ổ nguồn.'))

SECTIONS.append(('Nhận diện ADS đã xác nhận', 'Tên ADS đã được người dùng xác nhận lưu trong approved_ads.json, dùng chung cho mọi EP. Lựa chọn Browse mới nhất được ưu tiên cho đúng tên ADS đó; các tên khác vẫn dùng ADS Catalog. Chỉ ghép đúng tên đã xác nhận; không tự đoán tên tương tự. Các file đi kèm là temp theo thời lượng nguồn.'))

SECTIONS.append(('Sắp xếp ADS cuối ngày', 'Canh cuối ngày: giữ ADS ưu tiên, DO_NOT_SKIP và ADS theo quy tắc của các show được giữ lại. Dời ADS dưới 2 phút ở giữa show vào khe trong show cùng cycle; không dời M intro hoặc vị trí khóa theo profile. Nếu cần, bỏ ADS thường ở giữa show để dành chỗ cho tối đa một ADS dài từ INPUT_4 đã nhận diện và được phép phát. Không làm trống khe chèn bắt buộc khi canh MT.'))

SECTIONS.append(('Phương án cuối: bỏ intro sau MT', 'SMTV INTRO không bắt buộc: được bỏ sau MT khi cần canh cuối ngày. Trước hết thử Max/No Max, giữ show trọn vẹn, dời ADS ngắn, bỏ ADS thường và thêm tối đa một ADS phù hợp. Nếu vẫn chưa đạt ±15 giây, mới thử bỏ từng M intro Long/Short sau MT và tính lại cả show tiếp theo; ưu tiên bỏ ít intro nhất. Không bỏ intro trước MT. Báo cáo ghi rõ intro đã bỏ.'))

SECTIONS.append(('Lọc phiên bản trùng tên', 'Khi nhiều file ra cùng tên local, giữ phiên bản cao nhất; cùng phiên bản thì giữ file sửa mới nhất. Việc loại bản cũ dùng cờ nội bộ, không phụ thuộc giao diện Việt/Anh. Nếu vẫn chưa phân biệt được, thông báo liệt kê tên local trùng và từng file nguồn để kiểm tra.'))

SECTIONS.append(('QC: show kế tiếp', 'QC cuối ngày hiển thị show kế tiếp theo thứ tự cycle chưa cắt, cùng tổng thời lượng các phần của show (gồm IN/MAIN/OUT nếu có; không gồm ADS hoặc M intro chèn). Nếu không còn dữ liệu show tiếp theo trong các cycle đã dựng thì báo rõ, không đoán thời lượng.'))

SECTIONS.append(('QC: thời lượng NWN kế tiếp', 'Riêng show kế tiếp trong QC: nếu là NWN thì thời lượng không tính Daily Scroll. Đây chỉ là thông tin tham khảo của show tiếp theo; NWN thực sự ở cuối lịch vẫn có thể giữ hoặc bỏ Daily Scroll theo cách canh giờ.'))

SECTIONS.append(('Teaser đúng ngày', 'Teaser thường có số EP chỉ lấy đúng EP ngày mai (EP đang làm + 1), ví dụ 3312 chỉ lấy TSER 3313, bỏ 3315. Áp dụng cả nguồn W, file local cũ và khi dựng lịch. AP giữ nguyên quy tắc chiến dịch trước 2 ngày, trước 1 ngày và TODAY; teaser FN không ghi số EP vẫn theo ô chọn hiện có. Không xóa file nguồn.'))

SECTIONS.append(('QC: thời lượng show và ADS', 'Thời lượng show kế tiếp trong QC bỏ các ADS ngoài show và M intro chèn. Chỉ với show có đúng S1 và S2, cộng mục chèn giữa hai segment và ghi riêng thời lượng đã cộng. NWN vẫn không tính Daily Scroll; IN/MAIN/OUT là phần của chương trình nên được tính.'))

SECTIONS.append(('Ngoại lệ cuối cùng cho 24h', 'Mốc 24h: sau khi mọi phương án thường và bỏ M intro sau MT vẫn không đạt, được thử bỏ ADS PRIORITY/DO_NOT_SKIP sau MT để giữ thêm show trọn vẹn; không bỏ mục chèn bắt buộc giữa segment. Nếu vẫn không đạt, nối đúng một show kế tiếp theo vòng lịch và cho phép vượt giờ. QC ghi ADS đã bỏ, mốc trước ngoại lệ, mốc cũ trước khi nối, show thêm, mốc mới và lý do. Mốc ngoài ±15 giây vẫn hiện cảnh báo, không báo đạt giả. Không thay đổi phần trước MT.'))

SECTIONS.append(('Mở ứng dụng', 'Thư mục chính chỉ để hai file mở ứng dụng INPUT và SCHEDULER (tên cũ PIP). Workbook INPUT.xlsx và portable_settings.json đặt trong schedule/pipeline/_NOI_BO. Công cụ phụ nằm trong tools; bộ ZIP nằm trong tools/distribution. Các thư mục media và playlist giữ đường dẫn hiện có.'))

SECTIONS.append(('Bộ gọn không kèm Office', 'Bộ gọn: INPUT.xlsx đặt ở thư mục chính cạnh SCHEDULER. Mở/sửa bảng bằng Excel hoặc ứng dụng bảng tính đã cài trên máy. Gói portable không kèm LibreOffice; Python và FFmpeg vẫn đi kèm để chạy Scheduler.'))

SECTIONS[:] = [item for item in SECTIONS if item[0] not in ('Bộ portable', 'Mở ứng dụng')]

SECTIONS.append(('Run all: chọn file còn thiếu', 'Run all kiểm tra trước khi tạo EP: hỏi cả ADS thường chưa tìm thấy. Chọn từng mục rồi Browse; với S1B chọn P1A hoặc thư mục để xem và xác nhận cả bộ cùng EP/sự kiện, không trộn reair khác. Lựa chọn S1B/teaser được lưu theo EP. ADS được tạo temp đúng thời lượng nếu nằm ngoài máy local và lưu liên kết tên dùng lại cho các EP sau. Recheck kiểm tra lại và tiếp tục; có thể dừng hoặc tiếp tục với lỗi còn lại. Sau dựng lịch, lỗi QC cũng hiện trong cửa sổ để xem và chạy lại. Không tự sửa lỗi canh giờ bằng cách chọn file bất kỳ.'))

SECTIONS.append(('Kiểm tra DN trong Run all', 'Daily News Scroll trong INPUT là DN của NWN, không phải ADS riêng. DN TEMP vẫn được nhận thành NWN Daily Scroll. Cửa sổ file thiếu không hỏi lại nhãn ADS này; kiểm tra chương trình NWN trong QC vẫn báo nếu thiếu Daily Scroll thật.'))

SECTIONS.append(('Chọn file ngay trên từng dòng', 'Trong cửa sổ file thiếu, khi bật FN luôn hiển thị S1B dù đã tìm thấy để có thể chọn lại bộ. Mỗi file có nút Browse riêng; S1B có thêm Folder. Status báo đỏ khi thiếu hoặc chọn lỗi; sau khi kiểm tra và lưu thành công hiện dấu xanh. ADS đã nhận diện không bị hỏi lại. Nếu không có mục thiếu/lỗi, Run all tiếp tục không mở cửa sổ này.'))

SECTIONS[:] = [item for item in SECTIONS if item[0] != 'Chọn file ngay trên từng dòng']
SECTIONS.append(('File thiếu và tên ADS', 'Cửa sổ chỉ hiển thị mục thiếu hoặc lỗi; S1B đã có thì không hiện. Mỗi mục thiếu có Browse riêng; chọn thành công hiện dấu xanh. Nhận diện ADS bỏ khác biệt chữ hoa, dấu phân cách, thời lượng, tiền tố NEW/AD và hậu tố phiên bản v1/v2 khi chỉ có một file khớp. Giữ số và nội dung tên; nhiều file khớp thì hỏi. Tên viết tắt khác nội dung dùng liên kết đã xác nhận; không tự đoán.'))

SECTIONS.append(('ADS ưu tiên trước SMTV INTRO', 'SMTV INTRO là ADS thường: chỉ được đứng đầu cycle nếu giữ, không được chiếm chỗ làm mất ADS ưu tiên cuối cycle trước. Khi chia slot, giữ ADS theo profile/quy tắc và DO_NOT_SKIP, rồi PRIORITY, rồi teaser/ADS thường; INTRO bị bỏ không chuyển vào giữa show. Khi canh MT, thử Max/No Max và thêm/dời/bỏ ADS thường, gồm SMTV INTRO, trên các cycle gần rồi xa trước. Chỉ khi các phương án giữ PRIORITY đều không đạt ±15 giây mới cho phép bỏ PRIORITY không khóa profile. QC ghi rõ INTRO và ADS đã bỏ; quy tắc một mục mỗi khe và ADS dài giữa show vẫn giữ.'))

SECTIONS.append(('Nối NWN cuối ngày chỉ đến S3', 'Khi dùng ngoại lệ nối thêm show kế tiếp để kết ngày, nếu show đó là NWN thì chỉ lấy nội dung S1A, bộ S1B, S1C, S2 và hết S3. Không kéo theo teaser, Daily Scroll hoặc ADS cuối NWN. Thiếu S3 phải báo lỗi, không nối bộ thiếu. Quy tắc này chỉ áp dụng NWN được nối thêm ở bước cuối; NWN thường vẫn theo quy tắc canh giờ hiện có.'))

SECTIONS[:] = [item for item in SECTIONS if item[0] not in ('6. Canh cuối ngày', 'Sắp xếp ADS cuối ngày', 'Phương án cuối: bỏ intro sau MT', 'Ngoại lệ cuối cùng cho 24h')]
SECTIONS.insert(9, ('Canh cuối ngày: ưu tiên và phối hợp', 'Khi thiếu giờ tới mốc cuối ngày: ưu tiên thêm Max có sẵn, đưa ADS dài ở phần cuối cycle bị bỏ lên thay ADS ngắn giữa hai show, rồi thêm/thay một ADS từ danh sách INPUT_4 ở một vị trí. Nếu chưa đạt, thử kéo đúng show kế tiếp lên; tính lại từ lịch gốc để không giữ ADS bù cho phương án kết thúc cũ. Ưu tiên bỏ ADS thường (gồm SMTV INTRO), mục chèn giữa FN/NWN, M intro Long/Short, ADS ưu tiên/DO_NOT_SKIP, cuối cùng tối đa một Daily Scroll sau MT. Đây là ưu tiên: có thể phối hợp Max, bỏ và thay ADS để đạt giờ. Luôn giữ một mục chèn dưới 2 phút giữa các segment của show; không thay phần trước MT. NWN nối thêm chỉ tới hết S3, không teaser/DN/ADS cuối. Nếu tìm không được phương án đạt ±15 giây thì cho phép vượt và báo rõ trong QC; nếu tìm kiếm chạm giới hạn thì báo rõ, không khẳng định đã thử mọi tổ hợp.'))

SECTIONS.append(('Teaser FN nguồn thay temp cũ', 'Khi nguồn EP có teaser FN thật, dùng các teaser FN đã quét từ nguồn và bỏ lựa chọn tay/temp FN cũ khỏi danh sách dựng lịch. Không dùng tên temp cũ làm teaser SHOW. Nếu nguồn có nhiều teaser FN thật vẫn hỏi chọn; không tự đoán. Browse teaser FN chỉ nhận file TSER/TEASER FN, không nhận chương trình S1B.'))

SECTIONS.append(('Cột thời gian All cycles', 'All cycles: Length là thời lượng riêng của từng mục; End là thời gian cộng dồn từ đầu playlist đến hết mục đó, không đặt lại ở đầu mỗi cycle.'))

SECTIONS.append(('Dịch vị trí MT theo số show', 'MT shift (shows) chọn từ -5 đến +5 và nhớ lần chọn cuối. 0 dùng vị trí tự động bình thường. Số âm chọn ranh giới sớm hơn, số dương muộn hơn đúng số show so với kết quả tự động của cùng dữ liệu. Một show tính theo block, không theo segment hay ADS. Sau khi chọn ranh giới, tính lại Max/ADS và cuối ngày; mốc giờ MT vẫn giữ như cũ. Nếu không canh được ±15 giây thì báo QC, không tự bỏ lựa chọn và nhảy sang show khác. Ngoài số show đã dựng thì báo lỗi.'))

SECTIONS.append(('Cập nhật chương trình qua GitHub', 'Update PIP kiểm tra và tải các file chương trình đã thay đổi. INPUT.xlsx chỉ được thay khi tích chọn; sao lưu trước khi thay. Đóng Scheduler rồi áp dụng cập nhật và mở lại. Khi áp dụng lỗi sẽ cố gắng phục hồi bản trước và báo lỗi. Không thay ADS, EP, playlist, cấu hình hoặc lịch sử nhận diện. Máy chưa có nút này cần nhận bộ portable mới một lần.'))

SECTIONS.append(('Thư mục trong cửa sổ file thiếu', 'Cột Folder giữa Type và File / QC issue hiển thị nguyên tiêu đề nhóm ADS trong INPUT để tìm thư mục nguồn. Đây là gợi ý theo bảng, không phải đường dẫn đã xác minh. Mục không có tiêu đề nhóm hiển thị dấu gạch ngang.'))

SECTIONS.append(('Bỏ qua ADS trong ngày', 'Trong cửa sổ file thiếu, Skip today cạnh Browse bỏ ADS khỏi EP đang làm, kể cả ADS ưu tiên và ADS bù cuối ngày. Lưu riêng theo EP; ngày khác không bị ảnh hưởng. Bấm Recheck and continue để tính lại. Undo skip hoặc Browse thành công trên dòng đang mở sẽ hủy bỏ qua. Không xóa file và không đổi bảng nhận diện chung.'))

SECTIONS.append(('Start notice diagnostics', 'Unknown program notices show the unrecognized text, accepted program codes for the current EP and how to correct it. VEGC is accepted for an active Veganism Cooking Show. Recognized programs in the wrong order report the current block order.'))

SECTIONS.append(('VEGC and NWN filename recognition', 'Veganism Cooking Show uses VEGC in source naming, schedule blocks and BMD UP NXT selection. NWN filenames with the EP after NWN, such as NWN 3316 SEG 1A, are normalized to the same segment names as 3316 NWN SEG 1A. Rescan and create EP again after changing recognition rules.'))

SECTIONS.append(('Episode number before or after program code', 'Recognizes both EP CODE and CODE EP filename prefixes for NWN, BMD, WOW, AP, DN and active show codes. FN set detection and manual FN selection accept both orders. Numbers inside titles and teaser episode numbers are preserved.'))

SECTIONS.append(('Fallback teaser between segments', 'When a required segment gap has no available regular teaser or short ADS, use a valid teaser for this airing day under 120 seconds. Prefer the least-used teaser; repetition is allowed only for this fallback. Next-day EP, AP campaign phase and FN checkbox eligibility still apply. If none is short enough, report the missing insertion.'))

SECTIONS.append(('Consistency checks for source names and skipped ADS', 'IN/MAIN/OUT role detection accepts CODE EP as well as EP CODE. ADS skipped for the current EP are also blocked by reserve-catalog name matching. Regular short ADS are used before the emergency teaser fallback; fallback still requires a valid airing-day teaser shorter than 120 seconds.'))

SECTIONS.append(('Missing daily ADS input', 'The first Run all check warns when INPUT_3 has no row for the current EP, or when that row exists but contains no ADS. Update and save INPUT.xlsx, stop Run all and Scan EP again. Continuing remains a deliberate choice.'))
